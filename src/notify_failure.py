"""자동 실행이 실패했을 때 슬랙으로 '생성 실패 + 사유 확인 링크'를 보낸다."""
import os

from dotenv import load_dotenv

import publish

load_dotenv(publish.ROOT / ".env")
run_url = os.getenv("RUN_URL", "(실행 기록 링크 없음)")
publish.send_slack(
    "⚠️ 이번 주말 확정안 생성에 실패했어요.\n"
    f"사유 확인: {run_url}\n"
    "지난번 대시보드는 그대로 남아 있어요. 필요하면 GitHub Actions 에서 'Run workflow' 로 다시 실행하세요."
)
