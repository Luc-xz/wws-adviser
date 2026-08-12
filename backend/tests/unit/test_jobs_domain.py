"""Jobs 状态机测试（6_MODEL_AND_REPORT_PIPELINE.md §8.2）。"""

import pytest

from wws_adviser.modules.jobs.domain import JobStatus, can_transition


@pytest.mark.parametrize(
    "src,dst,expected",
    [
        (JobStatus.PENDING, JobStatus.RUNNING, True),
        (JobStatus.PENDING, JobStatus.CANCELLED, True),
        (JobStatus.RUNNING, JobStatus.COMPLETED, True),
        (JobStatus.RUNNING, JobStatus.RETRY_WAIT, True),
        (JobStatus.RUNNING, JobStatus.PARTIAL, True),
        (JobStatus.RUNNING, JobStatus.FAILED, True),
        (JobStatus.RUNNING, JobStatus.CANCELLED, True),
        (JobStatus.RETRY_WAIT, JobStatus.RUNNING, True),
        # 非法
        (JobStatus.PENDING, JobStatus.COMPLETED, False),
        (JobStatus.COMPLETED, JobStatus.RUNNING, False),
        (JobStatus.FAILED, JobStatus.RUNNING, False),
        (JobStatus.CANCELLED, JobStatus.RUNNING, False),
        (JobStatus.COMPLETED, JobStatus.FAILED, False),
    ],
)
def test_can_transition(src: JobStatus, dst: JobStatus, expected: bool) -> None:
    assert can_transition(src, dst) is expected
