"""Read back the first MiB of userdata through lidar_install's bounded fetch."""
import sys
from pathlib import Path

sys.path.insert(0, '/workspace/libreecho/private/forks/LibreEcho-Platform/tools/mt8167-arm64/install')
import lidar_install as li  # noqa: E402

image = Path(sys.argv[1])
log = li.RunLog(Path('logs/userdata-readback-2.raw.log'), 'userdata-readback')
fb = li.Fastboot('fastboot', log)
rb = fb.fetch_range('userdata', 0, li.MAX_FETCH_SIZE)
exp = li.sparse_prefix(image, len(rb))
print('bytes', len(rb), 'match', rb == exp, 'label', li.superblock_label(rb.ljust(2048, b'\0')))
