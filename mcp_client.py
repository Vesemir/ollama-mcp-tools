import asyncio
import typing
from typing import Optional
from functools import partial
from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
from ollama import chat
import os
import sys
import requests
import json


def chop_out_think(message):
    if '</think>' not in message.content:
        return
    message.content = message.content.split('</think>')[1]
    return
 


def add_two_numbers(a: int, b: int) -> int:
    """
    Add two numbers
  
    Args:
      a: The first integer number
      b: The second integer number
  
    Returns:
      int: The sum of the two numbers
    """
    return a + b


TOOL_MAP = {
    # add your own MCP tool here if required
    'add_two_numbers': add_two_numbers,
}


class MCPClient:
    def __init__(
            self, model: str = 'qwen3:30b-a3b', extra_system_prompt: str = '',
            keep_alive: int = None, creative=False, num_ctx: int = 2048):
        self.sessions : Dict[str, ClientSession] = {}
        self.unique_sessions: list[ClientSession] = []
        self.exit_stack = AsyncExitStack()
        self.extra_system_prompt = extra_system_prompt
        if creative:
            temperature = 1.2
        else:
            temperature = 0
        self.chatter = partial(
            chat, 
            #model='llama3-groq-tool-use:latest',
            model=model,
            options={
                'temperature': temperature,
                'num_ctx': num_ctx
            },
            keep_alive=keep_alive
        )
        self.clean_session()

    def init_prompt(self):
        self.messages = [
            {
                'role': 'System',
                'content': 'Отвечай на русском. {}'.format(self.extra_system_prompt)
            },
        ]

    def clean_session(self):
        self.init_prompt()
        

    async def connect_to_server(self, server_scripts_paths: list[str]):
        for script in server_scripts_paths:
            print("iter %s started" % script)
            if script.endswith('.py'):
                command = 'python'
                args = [script]
            elif script.endswith('.exe'):
                command = script
                args = []
            else:
                command = 'npx'
                args = ['-y', '@modelcontextprotocol/server-filesystem', 'E:/TotallyNotML/mcp_mess/ollama-mcp']
            server_params = StdioServerParameters(command=command, args=args, env=None)
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

            await session.initialize()
            response = await session.list_tools()

            tools = response.tools
            print('\nConnected to server with tools: ', [tool.name for tool in tools])
            for tool in tools:
                self.sessions[tool.name] = session
            self.unique_sessions.append(session)
            print("iter %s done" % script)

    async def process_query(self, query: str, stream=False) -> str:
        print("start processing new query...")
        self.messages.extend(
            [
                {
                    'role': 'user',
                    'content': query
                }
            ]
        )
        available_tools = []
        for session in self.unique_sessions:
            response = await session.list_tools()
            available_tools.extend([{
                'type': 'function',
                'function': {
                    'name': tool.name,
                    'description': tool.description,
                    'parameters': tool.inputSchema
                }
            } for tool in response.tools
            ])

        print("listed tools again...")
        response = self.chatter(
            messages=self.messages,
            tools=available_tools,
            stream=stream
        )
        print("got new response from llm...")

        final_text = []
        print(response.message)
        message = response.message
        while response.message.tool_calls:
            chop_out_think(response.message)
            self.messages.append(response.message)
            tool_num = len(response.message.tool_calls)

            for tool_info in response.message.tool_calls:
                print('[Calling tool {} with args {}'.format(
                    tool_info.function.name, tool_info.function.arguments
                    )
                )

                tool = TOOL_MAP.get(tool_info.function.name)
                if tool:
                    #print("Function output : {}".format()
                    result = tool(**tool_info.function.arguments)
                else:
                    result2 = await self.sessions[tool_info.function.name].call_tool(
                        tool_info.function.name, tool_info.function.arguments
                    )
                    #print("[!] Function {} not found".format(tool_info.function.name))
                    result = result2.content
                    print("TOOL RESULT : {} <...>( total {})".format(
                        result[0].text[:200], len(result[0].text))
                    )

                self.messages.append({
                    'role': 'tool',
                    'content': str(result),
                    'name': tool_info.function.name
                })

            print("{} tools called, next iter...".format(tool_num))

            response = self.chatter(
                messages=self.messages,
                tools=available_tools,
                stream=stream
            )
            print('response next : ', response)
            chop_out_think(response.message)

            self.messages.append(response.message)

        final_text.append(response.message.content)

        return '\n'.join(final_text)

    async def chat_loop(self):
        print("Mcp client works...")
        print("quit to exit")

        while True:
            try:
                query = input('\n Query: ').strip()
                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print('\n' + response)
            except Exception as ex:
                print("Error : {}".format(ex))

    async def cleanup(self):
        await self.exit_stack.aclose()


    async def chat_iter(query):
        pass


async def main():
    if len(sys.argv) < 2:
        print('use with 2+ arguments, argument 2+ should be either:\n'
              'a) path to python mcp tool script that will be launched through stdio;\n'
              'b) path to equivalent binary mcp tool ending with .exe (look@https://github.com/nickclyde/duckduckgo-mcp-server, installed through pip)\n'
              'c) path to node.js mcp tool if it starts with "npx"(look @https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) '
              '(everything is installed separately or written by hand)'
        )

        sys.exit(1)

    client = MCPClient(num_ctx=15000)
    try:
        await client.connect_to_server(sys.argv[1:])
        await client.chat_loop()
    finally:
        await client.cleanup()
    

if __name__ == '__main__':
    asyncio.run(main())
