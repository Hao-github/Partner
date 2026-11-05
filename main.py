import argparse
import logging

from ai_butler import Agent
from ai_butler.config import config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="私人 AI 管家")
    parser.add_argument("--channel", choices=("cli", "qq"), default="cli", help="输入输出渠道")
    parser.add_argument(
        "--provider", choices=("openai", "deepseek"), help="模型供应商，默认读取配置"
    )
    parser.add_argument("--model", help="模型名称，默认读取配置")
    qq_mode = parser.add_mutually_exclusive_group()
    qq_mode.add_argument("--qq-check", action="store_true", help="只检查 QQ 凭据与网关")
    qq_mode.add_argument(
        "--qq-discover", action="store_true", help="接收私聊并显示 OpenID，不调用模型"
    )
    parser.add_argument("--session", default="default", help="会话名称")
    parser.add_argument("--verbose", action="store_true", help="输出基础运行日志")
    args = parser.parse_args(argv)
    if (args.qq_check or args.qq_discover) and args.channel != "qq":
        parser.error("--qq-check / --qq-discover 需要 --channel qq。")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        if args.qq_check or args.qq_discover:
            Agent.inspect(args.channel, discover=args.qq_discover, settings=config)
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
