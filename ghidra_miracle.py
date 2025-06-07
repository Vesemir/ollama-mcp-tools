import asyncio
import sys
import json
import requests
from contextlib import contextmanager
import binascii
import time
from ollama import chat
from ollama import ChatResponse
import numpy as np
import threading
from queue import Queue, Empty 

import mcp_client


async def init_models(tools):
    print("initing mcp client...")
    try:
        var_renamer_client = mcp_client.MCPClient(
            model='qwen3:30b-a3b',
            creative=False,
            num_ctx=25300,
            extra_system_prompt="""
            Ты будешь работать по алгоритму:
            1. Вначале ты получишь от пользователя имя функции
            2. Дальше ты декомпилируешь её с помощью decompile_function tool.
            3. Дальше ты можешь переименовывать переменные в данной функции с помощью rename_variable tool в зависимости от их использования и/или информации, связанной с используемыми рядом с ними строковыми константами.
            4. Когда посчитаешь, что достаточно переименовывать или ты не уверена что стоит переименовывать какие-то переменные, напиши вместо ответа EXIT(1). EXIT(1) это НЕ tool, просто напиши его в выводе и прекращай работу.
            5. Сообщай только о фактически выполненных переименованиях, о другом сообщать не нужно.
            Никаких дополнительных подтверждений НЕ ТРЕБУЕТСЯ, выполняй запрошенное СРАЗУ.
            6. Если ты переименовываешь саму функцию, над которой работаешь, то дальше нужно в rename_variables передавать НОВОЕ имя, которое ты дала функции, а НЕ СТАРОЕ.
            7. Саму функцию переименовывай только после того, как переименовала в ней все переменные, которые хотела.
            """,
            keep_alive=0
        )
        await var_renamer_client.connect_to_server(tools)
        print("inited")
    except Exception as ex:
        print("couldn't init mcp 1 : {}".format(str(ex)))
        await var_renamer_client.cleanup()
        return

    print("initing mcp client...")
    try:
        string_reader_client = mcp_client.MCPClient(
            model='qwen3:30b-a3b',
            creative=False,
            num_ctx=25300,
            extra_system_prompt="""
            Ты будешь работать по алгоритму:
            1. Вначале ты получишь от пользователя имя функции
            2. Дальше ты декомпилируешь её с помощью decompile_function tool.
            3. Дальше ты посмотришь на числовые константы, используемые в функции.
            4. Если какие-то из них полностью преобразуемы к читабельным ascii-строкам, ты их напечатаешь и укажешь, в каких переменных они хранятся, например (buffer_1 -> "P@ssw0rd").
            Никаких дополнительных подтверждений НЕ ТРЕБУЕТСЯ, выполняй запрошенное СРАЗУ.
            5. Когда посчитаешь, что все ASCII-строки найдены, напиши вместо ответа EXIT(1). EXIT(1) это НЕ tool, просто напиши его в выводе и прекращай работу
            """,
            keep_alive=0
        )
        await string_reader_client.connect_to_server(tools)
        print("inited")
    except Exception as ex:
        print("couldn't init mcp 2 : {}".format(str(ex)))
        await string_reader_client.cleanup()
        return

    try:
        func_renamer_client = mcp_client.MCPClient(
            model='qwen3:30b-a3b',
            creative=False,
            num_ctx=25300,
            extra_system_prompt="""
            Ты будешь работать по алгоритму:
            1. Вначале ты получишь от пользователя имя функции
            2. Дальше ты декомпилируешь её с помощью decompile_function tool.
            3. Дальше ты можешь переименовывать функции внутри данной функции с помощью rename_function tool, если уверена, что твоё переименование повышает информативность.
            4. Для получения дополнительной информации о вложенных функциях также можно декомпилировать их с помощью decompile_function tool.
            5. Когда посчитаешь, что достаточно переименовывать или ты не уверена что стоит переименовывать какие-то функции, напиши вместо ответа EXIT(1). EXIT(1) это НЕ tool, просто напиши его в выводе и прекращай работу
            6. НЕ ПЕРЕИМЕНОВЫВАЙ, если разницы в семантике между новым и старым именем нет, а меняется только code style (snake case/camel case etc.)
            7. Сообщай только о фактически выполненных переименованиях, о другом сообщать не нужно.
            Никаких дополнительных подтверждений НЕ ТРЕБУЕТСЯ, выполняй запрошенное СРАЗУ.
            8. Если ты переименовываешь саму функцию, над которой работаешь, то дальше нужно в rename_variables передавать НОВОЕ имя, которое ты дал функции, а НЕ СТАРОЕ.
            """,
            keep_alive=0
        )
        await func_renamer_client.connect_to_server(tools)
        print("inited")
    except Exception as ex:
        print("couldn't init mcp 3: {}".format(str(ex)))
        await func_renamer_client.cleanup()
        return

    return func_renamer_client, string_reader_client, var_renamer_client


def break_on_stop_word(stop_words, text):
    text = text.lower()
    return any(stop_signs in text.lower() for stop_signs in stop_words)


async def main():
    if len(sys.argv) < 2:
        print('specify path to installed ghidra mcp tool (install its requirements beforehand):\n'
              'python ghidra_miracle.py /path/to/bridge_mcp_ghidra.py'
        )
        sys.exit(1)

    tools = sys.argv[1:]
    models = await init_models(tools)
    if models is None:
        print("Failure on initialization")
        return

    var_renamer_client, string_reader_client, func_renamer_client = models
    print("Chat starting ...")
    print("Mcp client works...")
    print("quit to exit")
    #functions = requests.get('http://localhost:8080/list_functions').text
    #function_list = [each.split('at')[0].strip() for each in functions.split('\n')]
    #filtered_function_list = [each for each in function_list if each.startswith('FUN_')]

    try:
        #for idx, func_name in enumerate(filtered_function_list, 1):
        while True:
            func_name = input('\n Следующая функция (для выхода /quit): ').strip()
            if func_name.lower() in ('/quit', '/exit', '/q', '/e'):
                break

            while True:
                response = await var_renamer_client.process_query(
                    'Function name is {}'.format(func_name)
                )
                print('\n' + response)
                if 'EXIT' in response:
                    print("exiting var rename loop...")
                    break

            # clear context from previous interaction
            var_renamer_client.clean_session()

            while True:
                response = await string_reader_client.process_query(
                    'Function name is {}'.format(func_name)
                )
                print('\n' + response)
                if 'EXIT' in response:
                    print("exiting string reader loop...")
                    break

            # clear context from previous interaction
            string_reader_client.clean_session()

            while True:
                response = await func_renamer_client.process_query(
                    'Function name is {}'.format(func_name)
                )
                print('\n' + response)
                if 'EXIT' in response:
                    print("exiting func rename loop...")
                    break

            #print("Decompiled function {}({} from {})".format(
            #    func_name, idx, len(filtered_function_list))
            #)

            # clear context from previous interaction
            func_renamer_client.clean_session()
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        var_renamer_client.cleanup()
        string_reader_client.cleanup()

        func_renamer_client.cleanup()

    print("Done, sleep now...")


if __name__ == '__main__':
    asyncio.run(main())
