import argparse
import logging

from ai_butler import Agent
from ai_butler.config import config


def main(argv=None) -> int:
    """解析启动参数并运行 Agent 或渠道诊断，将安全错误映射为退出码。"""
    parser = argparse.ArgumentParser(description="私人 AI 管家")
    parser.add_argument("--channel", default="cli", help="输入输出渠道，由内部工厂选择")
    parser.add_argument("--provider", help="模型供应商，默认读取配置")
    parser.add_argument("--model", help="模型名称，默认读取配置")
    diagnostics = parser.add_mutually_exclusive_group()
    diagnostics.add_argument("--check", action="store_true", help="检查所选渠道，不调用模型")
    diagnostics.add_argument("--discover", action="store_true", help="识别渠道发送者，不调用模型")
    parser.add_argument("--session", default="default", help="会话名称")
    parser.add_argument("--verbose", action="store_true", help="输出基础运行日志")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="{asctime} {levelname} {name} {message}",
        style="{",
    )
    try:
        if args.check or args.discover:
            Agent.inspect(args.channel, discover=args.discover, settings=config)
            return 0
        Agent(
            args.channel,
            provider=args.provider,
            model=args.model,
            session=args.session,
            settings=config,
        ).run()
        return 0
    except (ValueError, RuntimeError) as error:
        print(f"启动失败：{error}")
        return 2
    except KeyboardInterrupt:
        print("\n渠道接入已退出。")
        return 0
    except OSError:
        print("启动失败：无法读取配置或打开数据库，请检查目录权限和磁盘空间。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
