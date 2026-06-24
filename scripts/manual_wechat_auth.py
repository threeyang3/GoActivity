import asyncio
import os
import sys


def main() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "we-mp-rss"))
    os.chdir(repo_root)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from driver.wx import Wx

    async def run() -> None:
        wx = Wx()
        print(f"repo_root={repo_root}")
        print(f"qr_path={wx.wx_login_path}")
        print("Starting interactive WeChat auth flow...")
        await wx.wxLogin(NeedExit=False)
        print("WeChat auth flow finished.")

    asyncio.run(run())


if __name__ == "__main__":
    main()
