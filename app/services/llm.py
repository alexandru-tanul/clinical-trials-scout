"""LLM orchestration service for generating chat responses."""

import asyncio
import json
import time
from litellm import acompletion

from app.config import settings
from app.models import Chat, Message
from app.prompts import SYSTEM_PROMPT, LLM_TOOLS
from app.services.sse import notify_chat_update
from app.services.clinical_trials import smart_search_clinical_trials, search_clinical_trials
from app.services.drugcentral import query_drugcentral_database
from app.services.pharos import query_pharos_api


async def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments.

    Returns the tool result as a string.
    """
    if tool_name == "smart_search_clinical_trials":
        results = await smart_search_clinical_trials(
            search_term=arguments.get('search_term', ''),
            location=arguments.get('location'),
            status=arguments.get('status'),
            phase=arguments.get('phase'),
            max_results=arguments.get('max_results', 5)
        )
        return json.dumps(results, indent=2)

    elif tool_name == "query_drugcentral_database":
        question = arguments.get('question', '')
        return await query_drugcentral_database(question)

    elif tool_name == "query_pharos_api":
        question = arguments.get('question', '')
        return await query_pharos_api(question)

    # Backward compatibility for old tool name
    elif tool_name == "search_clinical_trials":
        results = await search_clinical_trials(
            query=arguments.get('query'),
            condition=arguments.get('condition'),
            intervention=arguments.get('intervention'),
            location=arguments.get('location'),
            status=arguments.get('status'),
            phase=arguments.get('phase'),
            max_results=arguments.get('max_results', 5)
        )
        return json.dumps(results, indent=2)

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


async def generate_response(chat: Chat) -> str:
    """Generate an LLM response for the given chat with streaming support.

    Uses agentic loop to:
    1. Call LLM with tools (streaming enabled)
    2. Execute any requested tools
    3. Feed results back to LLM
    4. Repeat until LLM provides final answer

    Streams responses to UI via SSE for real-time updates.
    Saves all messages to database in standard OpenAI format.

    Returns the final assistant message content.
    """
    try:
        # Build message history for LLM
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        llm_messages.extend(await chat.as_openai_api_format())

        # Agentic loop: Allow multiple rounds of tool calling
        max_iterations = 5
        iteration = 0
        final_message = ""

        while iteration < max_iterations:
            iteration += 1

            # Create placeholder assistant message for streaming
            assistant_msg = await chat.add_assistant_message(content="", tool_calls=None)
            await notify_chat_update(chat.id)

            # Call LLM with streaming enabled
            response = await acompletion(
                model=settings.MODEL,
                messages=llm_messages,
                tools=LLM_TOOLS,
                tool_choice="auto",
                stream=True,
                timeout=60.0,
            )

            # Accumulate streaming response
            content_buffer = ""
            tool_calls_buffer = []
            tool_calls_dict = {}  # For accumulating tool call deltas by index
            last_update_time = time.time()
            last_update_length = 0

            async for chunk in response:
                delta = chunk.choices[0].delta

                # Accumulate content
                if hasattr(delta, 'content') and delta.content:
                    content_buffer += delta.content

                    # Update DB every 0.5 seconds or every 100 characters
                    current_time = time.time()
                    should_update = (
                        current_time - last_update_time > 0.5 or
                        len(content_buffer) - last_update_length >= 100
                    )

                    if should_update:
                        assistant_msg.content = content_buffer
                        await assistant_msg.save()
                        await notify_chat_update(chat.id)
                        last_update_time = current_time
                        last_update_length = len(content_buffer)

                # Accumulate tool calls (they come as deltas)
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }

                        if hasattr(tc_delta, 'id') and tc_delta.id:
                            tool_calls_dict[idx]["id"] = tc_delta.id

                        if hasattr(tc_delta, 'function'):
                            if hasattr(tc_delta.function, 'name') and tc_delta.function.name:
                                tool_calls_dict[idx]["function"]["name"] = tc_delta.function.name
                            if hasattr(tc_delta.function, 'arguments') and tc_delta.function.arguments:
                                tool_calls_dict[idx]["function"]["arguments"] += tc_delta.function.arguments

            # Convert accumulated tool calls dict to list
            if tool_calls_dict:
                tool_calls_buffer = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]

            # Final update to database
            assistant_msg.content = content_buffer or None
            assistant_msg.tool_calls = tool_calls_buffer if tool_calls_buffer else None
            await assistant_msg.save()
            await notify_chat_update(chat.id)

            # If no tool calls, LLM is done
            if not tool_calls_buffer:
                final_message = content_buffer
                break

            # LLM wants to call tools - add to conversation
            llm_messages.append({
                "role": "assistant",
                "content": content_buffer or None,
                "tool_calls": tool_calls_buffer
            })

            # Execute tools and save results
            for tool_call in tool_calls_buffer:
                args = json.loads(tool_call["function"]["arguments"])
                print(f"[DEBUG] {tool_call['function']['name']} called with: {args}")

                # Execute the tool
                result = await execute_tool(tool_call["function"]["name"], args)
                print(f"[DEBUG] {tool_call['function']['name']} returned {len(result)} characters")

                # Save tool result message to database
                await chat.add_tool_message(
                    tool_call_id=tool_call["id"],
                    content=result,
                    name=tool_call["function"]["name"]
                )

                # Add to LLM conversation
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result
                })

            await notify_chat_update(chat.id)

            # Brief delay to make the process visible
            await asyncio.sleep(1.5)

        return final_message

    except Exception as e:
        await notify_chat_update(chat.id)
        raise
