import json
import uuid
from datetime import datetime, timezone

import markdown2
from fastapi import FastAPI, Request, Form, Cookie, Response, BackgroundTasks
from fastapi.responses import RedirectResponse
from jinja2_fragments.fastapi import Jinja2Blocks
from litellm import acompletion

from app.config import settings
from app.lifespan import lifespan
from app.models import Chat, Message, ResponseTask
from app.prompts import EXAMPLE_PROMPTS, LLM_TOOLS, SYSTEM_PROMPT
from app.services import search_clinical_trials

app = FastAPI(title="Clinical Trials Scout", lifespan=lifespan)
templates = Jinja2Blocks(directory=str(settings.TEMPLATES_DIR))


def get_status_message(status: str, elapsed_seconds: float) -> str:
    """Generate status message based on current status and elapsed time."""
    if status == "pending":
        return "Starting..."
    elif status == "analyzing":
        if elapsed_seconds > 15:
            return "Still analyzing your request..."
        return "Analyzing your request..."
    elif status == "tool_calling":
        if elapsed_seconds > 20:
            return "Still fetching data from ClinicalTrials.gov..."
        return "Fetching data from ClinicalTrials.gov"
    elif status == "synthesizing":
        if elapsed_seconds > 45:
            return "This is taking longer than usual..."
        elif elapsed_seconds > 20:
            return "Formatting the response..."
        return "Creating your results..."
    return "Processing..."


def md(text: str) -> str:
    """Convert markdown to HTML with better spacing and make links open in new tabs."""
    import re
    html = markdown2.markdown(
        text,
        extras=[
            'fenced-code-blocks',
            'tables',
            'break-on-newline',
            'cuddled-lists',
            'header-ids',
        ]
    )
    # Add target="_blank" and rel="noopener noreferrer" to all links for security
    html = re.sub(r'<a href="([^"]+)">', r'<a href="\1" target="_blank" rel="noopener noreferrer">', html)
    return html


async def generate_response_task(task_id: uuid.UUID, chat_id: int):
    """Background task to generate LLM response with status updates."""
    try:
        task = await ResponseTask.get(id=task_id)
        chat = await Chat.get(id=chat_id).prefetch_related("messages")

        # Update status: Analyzing request
        task.status = "analyzing"
        await task.save()

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m.role, "content": m.content} for m in chat.messages
        ]

        # Get LLM response (with optional tool use)
        response = await acompletion(model=settings.MODEL, messages=messages, tools=LLM_TOOLS, tool_choice="auto")
        assistant_message = response.choices[0].message

        if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
            # Update status: Calling tools
            task.status = "tool_calling"

            # Show initial thinking/summary if available
            if assistant_message.content:
                task.partial_content = md(assistant_message.content)

            await task.save()

            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": assistant_message.tool_calls
            })

            for tool_call in assistant_message.tool_calls:
                if tool_call.function.name == "search_clinical_trials":
                    args = json.loads(tool_call.function.arguments)
                    results = await search_clinical_trials(
                        condition=args.get('condition'),
                        intervention=args.get('intervention'),
                        location=args.get('location'),
                        status=args.get('status'),
                        max_results=args.get('max_results', 10)
                    )
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(results)})

            # Update status: Synthesizing results
            task.status = "synthesizing"
            await task.save()

            final_message = (await acompletion(model=settings.MODEL, messages=messages)).choices[0].message.content
        else:
            final_message = assistant_message.content

        # Save the message
        await Message.create(chat=chat, role="assistant", content=final_message)

        # Update task: Completed
        task.status = "completed"
        task.result = md(final_message)
        task.partial_content = None  # Clear partial content when done
        await task.save()

    except Exception as e:
        task = await ResponseTask.get(id=task_id)
        task.status = "error"
        task.error = str(e)
        await task.save()


@app.get("/")
async def index(request: Request):
    chats = await Chat.all().order_by("-updated_at")
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "example_prompts": EXAMPLE_PROMPTS,
            "chats": chats
        }
    )
    response.delete_cookie("chat_id")
    return response


@app.get("/chats/{chat_id}")
async def chat_detail(request: Request, chat_id: int):
    chat = await Chat.get_or_none(id=chat_id).prefetch_related("messages")
    if not chat:
        return RedirectResponse("/", status_code=302)

    chats = await Chat.all().order_by("-updated_at")
    messages = list(chat.messages)
    chat_history = [
        {"role": m.role, "content": md(m.content) if m.role == "assistant" else m.content}
        for m in messages
    ]

    # Check if we need to auto-generate a response (user message without assistant reply)
    needs_response = messages and messages[-1].role == "user"

    response = templates.TemplateResponse(
        request,
        "chat.html",
        {
            "chat_history": chat_history,
            "current_chat_id": chat_id,
            "chats": chats,
            "auto_generate": needs_response
        }
    )
    response.set_cookie("chat_id", str(chat_id), max_age=60*60*24*365)
    return response


@app.post("/send")
async def send_message(
    request: Request,
    message: str = Form(...),
    chat_id: str | None = Cookie(default=None)
):
    # Get or create chat
    if chat_id:
        chat = await Chat.get_or_none(id=int(chat_id))
    else:
        chat = None

    is_new = not chat
    if is_new:
        chat = await Chat.create(title=message[:50] + ("..." if len(message) > 50 else ""))

    await Message.create(chat=chat, role="user", content=message)
    await chat.save(update_fields=["updated_at"])

    if is_new:
        response = Response(status_code=200, headers={"HX-Redirect": f"/chats/{chat.id}"})
        response.set_cookie("chat_id", str(chat.id), max_age=60*60*24*365)
        return response

    return templates.TemplateResponse(
        request,
        "chat.html",
        {"message": {"role": "user", "content": message}},
        block_name="user_message",
        headers={"HX-Trigger": "generateResponse"}
    )


@app.get("/generate-response")
async def generate_assistant_response(
    request: Request,
    background_tasks: BackgroundTasks,
    chat_id: str | None = Cookie(default=None)
):
    if not chat_id:
        return templates.TemplateResponse(
            request,
            "chat.html",
            {},
            block_name="error_message"
        )

    chat = await Chat.get(id=int(chat_id)).prefetch_related("messages")

    # Check if the last message is already an assistant message
    messages = list(chat.messages)
    if messages and messages[-1].role == "assistant":
        # Response already exists, no need to generate
        return Response(status_code=204)  # No content

    # Check if there's already a pending or processing task for this chat
    existing_task = await ResponseTask.filter(
        chat=chat,
        status__in=["pending", "analyzing", "tool_calling", "synthesizing"]
    ).order_by("-created_at").first()

    if existing_task:
        # Resume the existing task instead of creating a new one
        elapsed = (datetime.now(timezone.utc) - existing_task.updated_at).total_seconds()
        status_message = get_status_message(existing_task.status, elapsed)

        return templates.TemplateResponse(
            request,
            "chat.html",
            {
                "task_id": str(existing_task.id),
                "status": existing_task.status,
                "status_message": status_message,
                "partial_content": existing_task.partial_content
            },
            block_name="status_indicator"
        )

    # Create a response task
    task_id = uuid.uuid4()
    await ResponseTask.create(
        id=task_id,
        chat=chat,
        status="pending"
    )

    # Start background task
    background_tasks.add_task(generate_response_task, task_id, chat.id)

    # Return status indicator that will poll for updates
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"task_id": str(task_id)},
        block_name="status_indicator"
    )


@app.get("/task-status/{task_id}")
async def task_status(request: Request, task_id: str):
    """Poll endpoint for task status updates."""
    task = await ResponseTask.get_or_none(id=uuid.UUID(task_id))

    if not task:
        return templates.TemplateResponse(
            request,
            "chat.html",
            {},
            block_name="error_message"
        )

    if task.status == "completed":
        # Return the completed message
        return templates.TemplateResponse(
            request,
            "chat.html",
            {"message": {"role": "assistant", "content": task.result}},
            block_name="assistant_message"
        )
    elif task.status == "error":
        return templates.TemplateResponse(
            request,
            "chat.html",
            {"error": task.error},
            block_name="error_message"
        )
    else:
        # Calculate elapsed time since last status update
        elapsed = (datetime.now(timezone.utc) - task.updated_at).total_seconds()
        status_message = get_status_message(task.status, elapsed)

        # Return updated status indicator with polling (and partial content if available)
        return templates.TemplateResponse(
            request,
            "chat.html",
            {
                "task_id": str(task_id),
                "status": task.status,
                "status_message": status_message,
                "partial_content": task.partial_content
            },
            block_name="status_indicator"
        )


@app.get("/chat")
async def chat_list(request: Request, search: str = ""):
    if search:
        chats = await Chat.filter(title__icontains=search).order_by("-updated_at")
    else:
        chats = await Chat.all().order_by("-updated_at")

    return templates.TemplateResponse(
        request,
        "base.html",
        {"chats": chats},
        block_name="chat_list"
    )


@app.post("/chats/{chat_id}/delete")
async def delete_chat(request: Request, chat_id: int, chat_id_cookie: str | None = Cookie(default=None, alias="chat_id")):
    chat = await Chat.get_or_none(id=chat_id)
    if not chat:
        return RedirectResponse("/", status_code=404)

    is_active = chat_id_cookie and int(chat_id_cookie) == chat_id
    await chat.delete()

    if is_active:
        response = Response(status_code=200, headers={"HX-Redirect": "/"})
        response.delete_cookie("chat_id")
        return response
    else:
        return Response(status_code=200, headers={"HX-Trigger": "refreshChats"})
