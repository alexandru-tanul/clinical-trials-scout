"""FastAPI application with routes only - business logic in services layer."""

import asyncio
import json
import markdown2
import re

from fastapi import FastAPI, Request, Form, Cookie, Response, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse, StreamingResponse
from jinja2_fragments.fastapi import Jinja2Blocks
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.deps import get_session_key
from app.lifespan import lifespan, chat_update_subscribers
from app.models import Chat, Message
from app.prompts import EXAMPLE_PROMPTS
from app.services.llm import generate_response
from app.services.sse import notify_chat_update


app = FastAPI(title="Clinical Trials Scout", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
templates = Jinja2Blocks(directory=str(settings.TEMPLATES_DIR))

# Enable auto-reload for templates in development
templates.env.auto_reload = settings.DEBUG
templates.env.cache_size = 0 if settings.DEBUG else 400

# Jinja filters
templates.env.filters['from_json'] = json.loads


def md(text: str | None) -> str:
    """Convert markdown to HTML with security."""
    if not text:
        return ""

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
    # Add target="_blank" and rel="noopener noreferrer" for security
    html = re.sub(r'<a href="([^"]+)">', r'<a href="\1" target="_blank" rel="noopener noreferrer">', html)
    return html


# Add markdown filter to Jinja
templates.env.filters['md'] = md


async def generate_response_task(chat_id: int):
    """Background task to generate LLM response."""
    try:
        chat = await Chat.get(id=chat_id)
        await generate_response(chat)
    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        # Could add error message to chat here


@app.get("/")
async def index(request: Request, session_key: str = Depends(get_session_key)):
    """Homepage with chat list and example prompts."""
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
    """Chat detail page."""
    chat = await Chat.get_or_none(id=chat_id, session_key=session_key)
    if not chat:
        return RedirectResponse("/", status_code=302)

    chats = await Chat.filter(session_key=session_key).order_by("-updated_at")
    chat_history = await chat.as_openai_api_format()

    response = templates.TemplateResponse(
        request,
        "chat.html",
        {
            "chat_history": chat_history,
            "chat_id": chat_id,
            "chats": chats
        }
    )
    response.set_cookie("chat_id", str(chat_id), max_age=60*60*24*365)
    return response


@app.post("/send")
async def send_message(
    request: Request,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    chat_id: str | None = Cookie(default=None),
    session_key: str = Depends(get_session_key)
):
    """Send a user message to a chat."""
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

    await chat.add_user_message(message)
    await notify_chat_update(chat.id)

    # Start background response generation
    background_tasks.add_task(generate_response_task, chat.id)

    if is_new:
        response = Response(status_code=200, headers={"HX-Redirect": f"/chats/{chat.id}"})
        response.set_cookie("chat_id", str(chat.id), max_age=60*60*24*365)
        return response

    return Response(status_code=204)


@app.get("/chat/{chat_id}/updates")
async def chat_updates_sse(
    request: Request,
    chat_id: int,
    session_key: str = Depends(get_session_key)
):
    """SSE endpoint for real-time chat updates."""
    chat = await Chat.get_or_none(id=chat_id, session_key=session_key)
    if not chat:
        return Response(status_code=404)

    async def event_stream():
        queue = asyncio.Queue()

        # Register subscriber
        if chat_id not in chat_update_subscribers:
            chat_update_subscribers[chat_id] = []
        chat_update_subscribers[chat_id].append(queue)

        try:
            while True:
                await queue.get()

                # Build updated chat content
                chat_history = await chat.as_openai_api_format()

                # Render content block
                response = templates.TemplateResponse(
                    request,
                    "chat.html",
                    {
                        "chat_history": chat_history,
                        "chat_id": chat_id
                    },
                    block_name="content"
                )

                # Extract HTML
                html = response.body.decode('utf-8')

                # Format as SSE
                lines = html.split('\n')
                sse_data = '\n'.join(f'data: {line}' for line in lines)

                yield f"event: chat-update\n{sse_data}\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            # Unregister subscriber
            if chat_id in chat_update_subscribers:
                try:
                    chat_update_subscribers[chat_id].remove(queue)
                    if not chat_update_subscribers[chat_id]:
                        del chat_update_subscribers[chat_id]
                except ValueError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/chat")
async def chat_list(request: Request, search: str = "", session_key: str = Depends(get_session_key)):
    """Search/list chats."""
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
    """Delete a chat."""
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
