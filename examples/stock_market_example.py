"""
A股行情数据MCP服务使用示例

展示如何使用A股行情数据MCP服务
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp_servers.stock_market.service import StockMarketService


async def main():
    """主函数"""
    print("=== A股行情数据MCP服务使用示例 ===\n")

    # 创建服务实例
    service = StockMarketService()

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

    print("4. 测试获取股票行情:")
    # 这里只是展示工具的存在，实际调用需要MCP客户端
    print("   工具已注册，可通过MCP客户端调用")
    print()

    print("5. 测试获取K线数据:")
    print("   工具已注册，可通过MCP客户端调用")
    print()

    print("=== 示例完成 ===")


if __name__ == "__main__":
    asyncio.run(main())
