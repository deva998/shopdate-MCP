"""Standard MCP handshake plus help calls only; never invokes doctor or run."""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


async def check():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    results=[]
    for route in ('jd','symc'):
        params=StdioServerParameters(command=sys.executable,
            args=['-B',str(ROOT/'shopdate.py'),route,'mcp'],cwd=str(ROOT),
            env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'})
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                init=await session.initialize()
                assert '不使用 Computer Use' in init.instructions
                tools=await session.list_tools()
                names=[x.name for x in tools.tools]
                assert {'doctor','commands','run','guide','workflow','workflow_catalog'}<=set(names)
                platforms=['jd'] if route=='jd' else ['sycm','alimama']
                for platform in platforms:
                    result=await session.call_tool('commands',{'platform':platform})
                    assert not result.is_error,(route,platform)
                result=await session.call_tool('guide',{})
                assert not result.is_error
                result=await session.call_tool('workflow_catalog',{})
                assert not result.is_error
                results.append({'route':route,'server':init.server_info.name,'tools':names,
                    'help_platforms':platforms,'business_requests':0})
    print(json.dumps({'status':'passed','results':results},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.dont_write_bytecode=True
    asyncio.run(check())
