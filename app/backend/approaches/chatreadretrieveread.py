import re
import logging
from typing import Any, AsyncGenerator, Optional, Union

import aiohttp
import openai
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
import pyodbc
import os
import time
import tempfile
import struct

from azure.identity import DefaultAzureCredential
from approaches.approach import Approach
from core.messagebuilder import MessageBuilder
from core.modelhelper import get_token_limit
from core.modelhelper import get_database_name
from text import nonewlines

class ChatReadRetrieveReadApproach(Approach):
    # Chat roles
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

    NO_RESPONSE = "0"

    """
    Simple retrieve-then-read implementation, using the Cognitive Search and OpenAI APIs directly. It first retrieves
    top documents from search, then constructs a prompt with them, and then uses OpenAI to generate an completion
    (answer) with that prompt.
    """

    schema_query = """
        SELECT concat(t.TABLE_SCHEMA, '.', t.TABLE_NAME, ' (', string_agg(c.COLUMN_NAME, ', '), ')') as tableInfo 
        FROM INFORMATION_SCHEMA.TABLES as t, 
        INFORMATION_SCHEMA.COLUMNS as c 
        WHERE t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE='BASE TABLE' 
        GROUP BY t.TABLE_SCHEMA, t.TABLE_NAME
    """

    def __init__(
        self,
        openai_host: str,
        azure_openai_url: str,
        azure_openai_key: str,
        chatgpt_deployment: Optional[str],  # Not needed for non-Azure OpenAI
        chatgpt_model: str,
        connection_string: str
    ):
        self.openai_host = openai_host
        self.azure_openai_url = azure_openai_url
        self.azure_openai_key = azure_openai_key
        self.chatgpt_deployment = chatgpt_deployment
        self.chatgpt_model = chatgpt_model
        self.connection_string = connection_string
        self.chatgpt_token_limit = get_token_limit(chatgpt_model)
        self.database_name = get_database_name(connection_string)

    def get_conn(self):
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
        SQL_COPT_SS_ACCESS_TOKEN = 1256  # This connection option is defined by microsoft in msodbcsql.h
        conn = pyodbc.connect(self.connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
        return conn

    async def schema_detect(self) -> str:
        folder = tempfile.gettempdir()
        schema_cache_file = folder + "/schema.txt"
        ts = time.time()
        schema_ttl = 60 * 60 # 1 hour
        if os.path.isfile(schema_cache_file) and ts - os.path.getmtime(schema_cache_file) < schema_ttl:
            with open(schema_cache_file, "r") as f:
                return f.read()
        else:
            conn = self.get_conn()

            cursor = conn.cursor()
            table_list = ""
            try:
                cursor.execute(self.schema_query)
                result = cursor.fetchall()
                for table in result:
                    table_list += table[0] + "\n"
            except:
                cursor.close()
                conn.close()
                return "No Tables Found"
            cursor.close()
            conn.close()
            with open(schema_cache_file, "w") as f:
                f.write(table_list)
            return table_list
    
    async def chat_response(self, query_result, commentary) -> any:
        response = ""
        if commentary != None:
            response = f"""{commentary}"""
        if query_result != None:
            if commentary != None:
                response += "\n### Results Returned\n"
            response += f"""{query_result}"""
        return {
            "choices": [
                {
                    "message": {
                        "content": response,
                        "role": "assistant"
                    },
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": "stop",
                    "session_state": None,
                }
            ],
        }

    async def get_result_from_database(self, sql_query: str, row_limit: int) -> dict[str, Any]:
        conn = self.get_conn()
        cursor = conn.cursor()
        output = ""
        result_type = "error"
        try:
            cursor.execute(sql_query)
            if cursor.description[0][0] == '':
                result_type = "scalar"
                for row in cursor.fetchall():
                    for column in row:
                        output += str(column)
            else:
                result_type = "table"
                row_count = 0
                column_count = 0
                
                output += "| "
                for column in cursor.description:
                    output += column[0] + " | "
                    column_count += 1
                output += "\n"

                output += "| "
                for i in range(column_count):
                    output += "--- | "
                output += "\n"
                
                for row in cursor.fetchall():
                    output += "| "
                    for column in row:
                        output += str(column) + " | "
                    output += "\n"
                    row_count += 1
                    if row_count >= row_limit:
                        break
        except Exception as e:
            logging.exception(str(e))
            result_type = "error"
            return str(e)
        cursor.close()
        conn.close()
        return {
            "result": output,
            "type": result_type
        }

    async def run_until_final_call(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        should_stream: bool = False,
    ) -> tuple:
        top = overrides.get("top", 10)
        original_user_query = history[-1]["content"]

        # Initialize the kernel
        kernel = sk.Kernel()

        kernel.add_service(
            AzureChatCompletion(
                service_id="chat_completion",
                deployment_name=self.chatgpt_deployment,
                endpoint=self.azure_openai_url,
                api_key=self.azure_openai_key
            ),
        )

        plugins_directory = "./approaches/plugins"

        query_plugin = kernel.add_plugin(
            parent_directory=plugins_directory, plugin_name="QueryPlugin"
        )

        response_token_limit = 1024
        messages_token_limit = self.chatgpt_token_limit - response_token_limit
        messages = self.get_messages_from_history(
            system_prompt="None",
            model_id=self.chatgpt_model,
            history=history,
            # Model does not handle lengthy system messages well. Moving sources to latest user conversation to solve follow up questions prompt.
            user_content=original_user_query,
            max_tokens=messages_token_limit,
        )

        msg_to_display = "\n".join([str(message) for message in messages])

        query_response = await kernel.invoke(query_plugin["nlpToSql"], input=original_user_query, 
                                        table_descriptions=await self.schema_detect(), 
                                        database_name=self.database_name, 
                                        history=msg_to_display)
        
        query_deformatted = str(query_response).replace("```sql", "").replace("```", "").strip()
        
        explanation_response = await kernel.invoke(query_plugin["explainSql"], input=str(query_deformatted), 
                                        original_question=original_user_query,
                                        table_descriptions=await self.schema_detect(), 
                                        database_name=self.database_name, 
                                        history=msg_to_display)

        logging.info(f"Query Response: {query_deformatted}")

        query_result = None

        query_result = await self.get_result_from_database(str(query_deformatted), top)

        extra_info = {
            "data_points": query_result["result"],
            "thoughts": f"Query:<br>{query_result}<br><br>Conversations:<br>"
            + msg_to_display.replace("\n", "<br>"),
        }

        commentary = str(explanation_response) + "\n```sql\n" + str(query_deformatted) + "\n```"

        chat_coroutine = self.chat_response(query_result["result"], commentary)
        return (extra_info, chat_coroutine)

    async def run_without_streaming(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        session_state: Any = None,
    ) -> dict[str, Any]:
        extra_info, chat_coroutine = await self.run_until_final_call(
            history, overrides, auth_claims, should_stream=False
        )
        chat_resp = dict(await chat_coroutine)
        chat_resp["choices"][0]["context"] = extra_info
        chat_resp["choices"][0]["session_state"] = session_state
        return chat_resp

    async def run_with_streaming(
        self,
        history: list[dict[str, str]],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        session_state: Any = None,
    ) -> AsyncGenerator[dict, None]:
        extra_info, chat_coroutine = await self.run_until_final_call(
            history, overrides, auth_claims, should_stream=True
        )
        yield {
            "choices": [
                {
                    "delta": {"role": self.ASSISTANT},
                    "context": extra_info,
                    "session_state": session_state,
                    "finish_reason": None,
                    "index": 0,
                }
            ],
            "object": "chat.completion.chunk",
        }

        async for event in await chat_coroutine:
            # "2023-07-01-preview" API version has a bug where first response has empty choices
            if event["choices"]:
                yield event

    async def run(
        self, messages: list[dict], stream: bool = False, session_state: Any = None, context: dict[str, Any] = {}
    ) -> Union[dict[str, Any], AsyncGenerator[dict[str, Any], None]]:
        overrides = context.get("overrides", {})
        auth_claims = context.get("auth_claims", {})
        async with aiohttp.ClientSession() as s:
            # openai.aiosession.set(s)
            response = await self.run_without_streaming(messages, overrides, auth_claims, session_state)
        return response

    def get_messages_from_history(
        self,
        system_prompt: str,
        model_id: str,
        history: list[dict[str, str]],
        user_content: str,
        max_tokens: int,
    ) -> list:
        message_builder = MessageBuilder(system_prompt, model_id)

        message_builder.append_message(self.USER, user_content)
        total_token_count = message_builder.count_tokens_for_message(message_builder.messages[-1])

        newest_to_oldest = list(reversed(history[:-1]))
        for message in newest_to_oldest:
            potential_message_count = message_builder.count_tokens_for_message(message)
            if (total_token_count + potential_message_count) > max_tokens:
                logging.debug("Reached max tokens of %d, history will be truncated", max_tokens)
                break
            message_builder.append_message(message["role"], message["content"])
            total_token_count += potential_message_count
        return message_builder.messages