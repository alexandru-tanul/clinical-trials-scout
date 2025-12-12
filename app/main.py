import asyncio
import json
import uuid
from datetime import datetime, timezone

import markdown2
from fastapi import FastAPI, Request, Form, Cookie, Response, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse
from jinja2_fragments.fastapi import Jinja2Blocks
from litellm import acompletion
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.deps import get_session_key
from app.lifespan import lifespan
from app.models import Chat, Message, ResponseTask
from app.prompts import EXAMPLE_PROMPTS, LLM_TOOLS, SYSTEM_PROMPT
from app.services import search_clinical_trials, smart_search_clinical_trials

app = FastAPI(title="Clinical Trials Scout", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
templates = Jinja2Blocks(directory=str(settings.TEMPLATES_DIR))


def get_status_message(status: str, elapsed_seconds: float) -> str:
    """Generate status message based on current status and elapsed time."""
    if status == "pending":
        return "Preparing to process your query..."
    elif status == "analyzing":
        if elapsed_seconds > 15:
            return "Still analyzing your request and determining search parameters..."
        return "Analyzing your request and determining search parameters..."
    elif status == "tool_calling":
        if elapsed_seconds > 20:
            return "Still searching ClinicalTrials.gov with multiple strategies..."
        return "Searching ClinicalTrials.gov with multiple strategies..."
    elif status == "synthesizing":
        if elapsed_seconds > 45:
            return "Finalizing synthesis... This is taking longer than usual..."
        elif elapsed_seconds > 20:
            return "Formatting results and generating research insights..."
        return "Analyzing trial data and preparing comprehensive summary..."
    return "Processing your request..."


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


def extract_thinking_and_text(message) -> tuple[str | None, str]:
    """
    Extract thinking and text content from LLM response.
    Returns (thinking_content, text_content).

    Handles both string responses and structured content blocks.
    """
    thinking_content = None
    text_content = ""

    # If content is a string, return it directly
    if isinstance(message.content, str):
        return None, message.content

    # If content is a list of blocks (thinking mode enabled)
    if isinstance(message.content, list):
        for block in message.content:
            if hasattr(block, 'type'):
                if block.type == "thinking":
                    thinking_content = block.thinking
                elif block.type == "text":
                    text_content += block.text
            elif isinstance(block, dict):
                if block.get('type') == "thinking":
                    thinking_content = block.get('thinking', '')
                elif block.get('type') == "text":
                    text_content += block.get('text', '')

    return thinking_content, text_content


async def generate_response_task(task_id: uuid.UUID, chat_id: int):
    """Background task to generate LLM response with status updates."""
    try:
        # Fetch task and chat
        task = await ResponseTask.get(id=task_id)
        chat = await Chat.get(id=chat_id).prefetch_related("messages")

        # Update status: Analyzing request
        task.status = "analyzing"
        await task.save()

        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m.role, "content": m.content} for m in chat.messages
        ]

        # First call: tools enabled but NO thinking
        # (Thinking + tools in same call causes Anthropic API conflicts)
        # Thinking will be used in synthesis call instead where it helps most
        response = await acompletion(
            model=settings.MODEL,
            messages=messages,
            tools=LLM_TOOLS,
            tool_choice="auto",
            timeout=60.0,  # 60 second timeout for initial analysis
        )
        assistant_message = response.choices[0].message

        if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
            # Update status: Calling tools
            task.status = "tool_calling"

            # Show initial thinking/summary if available
            if assistant_message.content:
                # Extract text content for display (might be string or list of blocks)
                display_content = assistant_message.content
                if isinstance(display_content, list):
                    # Extract text from blocks for display
                    text_parts = []
                    for block in display_content:
                        if hasattr(block, 'text'):
                            text_parts.append(block.text)
                        elif isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    display_content = '\n'.join(text_parts) if text_parts else ''
                if display_content:
                    task.partial_content = md(display_content)

            await task.save()

            # Collect all tool results
            all_tool_results = []
            for tool_call in assistant_message.tool_calls:
                if tool_call.function.name == "smart_search_clinical_trials":
                    args = json.loads(tool_call.function.arguments)
                    print(f"[DEBUG] smart_search called with: {args}")  # Debug logging
                    results = await smart_search_clinical_trials(
                        search_term=args.get('search_term', ''),
                        location=args.get('location'),
                        status=args.get('status'),
                        phase=args.get('phase'),
                        max_results=args.get('max_results', 5)
                    )
                    print(f"[DEBUG] smart_search returned: strategy={results.get('strategy_used')}, count={results.get('total_count')}")
                    all_tool_results.append({
                        "search_term": args.get('search_term', ''),
                        "results": results
                    })

                # Backward compatibility for old tool name
                elif tool_call.function.name == "search_clinical_trials":
                    args = json.loads(tool_call.function.arguments)
                    results = await search_clinical_trials(
                        query=args.get('query'),
                        condition=args.get('condition'),
                        intervention=args.get('intervention'),
                        location=args.get('location'),
                        status=args.get('status'),
                        phase=args.get('phase'),
                        max_results=args.get('max_results', 5)
                    )
                    all_tool_results.append({
                        "query": args.get('query') or args.get('condition') or args.get('intervention'),
                        "results": results
                    })

            # Brief delay to make the fetching status visible
            await asyncio.sleep(1.5)

            # Update status: Synthesizing results
            task.status = "synthesizing"
            await task.save()

            # Build a FRESH conversation for synthesis (no tool_calls history)
            # This avoids Anthropic API conflicts with thinking + tools
            user_query = chat.messages[-1].content if chat.messages else "clinical trials"

            # Format results summary for cleaner prompt
            results_summary = json.dumps(all_tool_results, indent=2)

            synthesis_prompt = f"""User asked: "{user_query}"

The search tool returned these results from ClinicalTrials.gov:

{results_summary}

IMPORTANT: Present these results to the user following your system instructions. Format as a table with research insights. Do NOT tell the user to search again or suggest alternative search terms - you are the search tool, present what was found. If results seem off-topic, still present them in a table and note the discrepancy briefly."""

            synthesis_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": synthesis_prompt}
            ]

            # Synthesis call with optional thinking (safe - no tool history)
            thinking_param = None
            if settings.ENABLE_THINKING:
                thinking_param = {
                    "type": "enabled",
                    "budget_tokens": settings.THINKING_BUDGET_TOKENS
                }

            synthesis_response = await acompletion(
                model=settings.SYNTHESIS_MODEL,
                messages=synthesis_messages,
                timeout=120.0,  # 120 second timeout for synthesis
                **({"thinking": thinking_param} if thinking_param else {})
            )

            # Extract thinking and text from synthesis response
            synthesis_thinking, final_message = extract_thinking_and_text(synthesis_response.choices[0].message)

            # Optionally prepend thinking content if configured
            if synthesis_thinking and settings.SHOW_THINKING:
                final_message = f"<details><summary> Extended Thinking Process</summary>\n\n{synthesis_thinking}\n\n</details>\n\n{final_message}"
        else:
            # Direct response (no tool use) - extract text content
            # Note: Thinking is not enabled for the first call (only synthesis)
            _, final_message = extract_thinking_and_text(assistant_message)

        # Save the message
        await Message.create(chat=chat, role="assistant", content=final_message)

        # Update task: Completed
        task.status = "completed"
        task.result = md(final_message)
        task.partial_content = None  # Clear partial content when done
        await task.save()

    except asyncio.TimeoutError:
        task = await ResponseTask.get(id=task_id)
        task.status = "error"
        task.error = "Request timed out. The API took too long to respond. Please try again."
        await task.save()
    except Exception as e:
        task = await ResponseTask.get(id=task_id)
        task.status = "error"
        task.error = f"An error occurred: {str(e)}"
        await task.save()


@app.get("/")
async def index(request: Request, session_key: str = Depends(get_session_key)):
    chats = await Chat.filter(session_key=session_key).order_by("-updated_at")
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
async def chat_detail(request: Request, chat_id: int, session_key: str = Depends(get_session_key)):
    chat = await Chat.get_or_none(id=chat_id, session_key=session_key).prefetch_related("messages")
    if not chat:
        return RedirectResponse("/", status_code=302)

    chats = await Chat.filter(session_key=session_key).order_by("-updated_at")
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
    chat_id: str | None = Cookie(default=None),
    session_key: str = Depends(get_session_key)
):
    # Get or create chat
    if chat_id:
        chat = await Chat.get_or_none(id=int(chat_id), session_key=session_key)
    else:
        chat = None

    is_new = not chat
    if is_new:
        chat = await Chat.create(
            title=message[:50] + ("..." if len(message) > 50 else ""),
            session_key=session_key
        )

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
    chat_id: str | None = Cookie(default=None),
    session_key: str = Depends(get_session_key)
):
    if not chat_id:
        return templates.TemplateResponse(
            request,
            "chat.html",
            {},
            block_name="error_message"
        )

    chat = await Chat.get_or_none(id=int(chat_id), session_key=session_key)
    if not chat:
        return templates.TemplateResponse(
            request,
            "chat.html",
            {},
            block_name="error_message"
        )

    await chat.fetch_related("messages")

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
    initial_status_message = get_status_message("pending", 0)
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "task_id": str(task_id),
            "status": "pending",
            "status_message": initial_status_message
        },
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
async def chat_list(request: Request, search: str = "", session_key: str = Depends(get_session_key)):
    if search:
        chats = await Chat.filter(session_key=session_key, title__icontains=search).order_by("-updated_at")
    else:
        chats = await Chat.filter(session_key=session_key).order_by("-updated_at")

    return templates.TemplateResponse(
        request,
        "base.html",
        {"chats": chats},
        block_name="chat_list"
    )


@app.post("/chats/{chat_id}/delete")
async def delete_chat(
    request: Request,
    chat_id: int,
    chat_id_cookie: str | None = Cookie(default=None, alias="chat_id"),
    session_key: str = Depends(get_session_key)
):
    chat = await Chat.get_or_none(id=chat_id, session_key=session_key)
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
