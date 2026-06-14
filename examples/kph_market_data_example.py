"""
开盘红平台行情数据MCP服务使用示例

展示如何使用开盘红平台行情数据MCP服务
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp_servers.kph_market_data.service import KPHMarketDataService


async def main():
    """主函数"""
    print("=== 开盘红平台行情数据MCP服务使用示例 ===\n")

    # 创建服务实例
    service = KPHMarketDataService()

    print("1. 服务信息:")
    info = service.get_server_info()
    print(f"   服务名称: {info['name']}")
    print(f"   服务版本: {info['version']}")
    print()

    print("2. 可用工具列表:")
    tools = await service.mcp.list_tools()
    for tool in tools:
        print(f"   - {tool.name}: {tool.description}")
    print()

    print("3. 可用资源列表:")
    resources = await service.mcp.list_resources()
    for resource in resources:
        print(f"   - {resource.uri}: {resource.name}")
    print()

    print("4. 功能说明:")
    print("   - 获取当日大盘直播内容")
    print("   - 获取当日涨停天梯数据")
    print("   - 获取当日盘面亮点数据")
    print("   - 获取历史大盘直播内容")
    print("   - 获取历史涨停天梯数据")
    print("   - 获取历史盘面亮点数据")
    print()

    print("5. 使用示例:")
    print("   通过MCP客户端调用以下工具:")
    print("   - get_live_content(): 获取当日大盘直播内容")
    print("   - get_limit_up_ladder(): 获取当日涨停天梯数据")
    print("   - get_market_highlights(): 获取当日盘面亮点数据")
    print("   - get_historical_live_content(date='2026-05-28'): 获取历史大盘直播内容")
    print("   - get_historical_limit_up_ladder(date='2026-05-28'): 获取历史涨停天梯数据")
    print("   - get_historical_market_highlights(date='2026-05-28'): 获取历史盘面亮点数据")
    print()

    print("=== 示例完成 ===")


if __name__ == "__main__":
    asyncio.run(main())