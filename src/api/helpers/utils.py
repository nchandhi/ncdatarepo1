# import dataclasses
import json
import logging
import os

# import requests

DEBUG = os.environ.get("DEBUG", "false")
if DEBUG.lower() == "true":
    logging.basicConfig(level=logging.DEBUG)

AZURE_SEARCH_PERMITTED_GROUPS_COLUMN = os.environ.get(
    "AZURE_SEARCH_PERMITTED_GROUPS_COLUMN"
)



def format_stream_response(chatCompletionChunk, history_metadata, apim_request_id):
    response_obj = {
        "id": chatCompletionChunk.id,
        "model": chatCompletionChunk.model,
        "created": chatCompletionChunk.created,
        "object": chatCompletionChunk.object,
        "choices": [{"messages": []}],
        "history_metadata": history_metadata,
        "apim-request-id": apim_request_id,
    }

    if len(chatCompletionChunk.choices) > 0:
        delta = chatCompletionChunk.choices[0].delta
        if delta:
            if hasattr(delta, "context"):
                messageObj = {"role": "tool", "content": json.dumps(delta.context)}
                response_obj["choices"][0]["messages"].append(messageObj)
                return response_obj
            if delta.role == "assistant" and hasattr(delta, "context"):
                messageObj = {
                    "role": "assistant",
                    "context": delta.context,
                }
                response_obj["choices"][0]["messages"].append(messageObj)
                return response_obj
            else:
                if delta.content:
                    messageObj = {
                        "role": "assistant",
                        "content": delta.content,
                    }
                    response_obj["choices"][0]["messages"].append(messageObj)
                    return response_obj

    return {}
