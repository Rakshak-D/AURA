from services.reminder_service import check_adaptive
from apscheduler.schedulers.blocking import BlockingScheduler
import time

sched = BlockingScheduler()
sched.add_job(lambda: check_adaptive(1), 'interval', hours=1)  # Hourly adaptive check
sched.start()