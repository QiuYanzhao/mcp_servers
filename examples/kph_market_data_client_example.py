"""
开盘红平台行情数据MCP客户端使用示例

展示如何使用MCP客户端调用开盘红平台行情数据服务
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    """主函数"""
    print("=== 开盘红平台行情数据MCP客户端使用示例 ===\n")

    # 创建服务器参数
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "start_kph_market_data_service.py"],
        cwd="/Users/qyz/TraeProjects/mcp_servers"
    )

    try:
        # 连接到服务器
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 初始化会话
                await session.initialize()

                print("1. 获取可用工具列表:")
                tools_result = await session.list_tools()
                print(f"   可用工具数量: {len(tools_result.tools)}")
                for tool in tools_result.tools:
                    print(f"   - {tool.name}")
                print()

                print("2. 调用工具示例:")
                print("   注意: 以下调用需要网络连接，可能失败")
                print()

                # 尝试获取当日大盘直播内容
                print("   尝试获取当日大盘直播内容:")
                try:
                    result = await session.call_tool("get_live_content", {})
                    print(f"   结果: {result.content[:100] if result.content else '无数据'}...")
                except Exception as e:
                    print(f"   调用失败: {e}")
                print()

                # 尝试获取当日涨停天梯数据
                print("   尝试获取当日涨停天梯数据:")
                try:
                    result = await session.call_tool("get_limit_up_ladder", {})
                    print(f"   结果: {result.content[:100] if result.content else '无数据'}...")
                except Exception as e:
                    print(f"   调用失败: {e}")
                print()

                print("=== 示例完成 ===")

    except Exception as e:
        print(f"连接服务器失败: {e}")
        print("请确保服务器正在运行，或者使用以下命令启动服务器:")
        print("  uv run python start_kph_market_data_service.py")


if __name__ == "__main__":
    asyncio.run(main())