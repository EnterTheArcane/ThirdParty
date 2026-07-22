import calendar
import time

def timestamp_now():
    # seconds since epoch 0, easy to store, in UTC
    # Used in Manifest timestamp, in packagesDB LRU and in timestamp of backup-sources json
    return calendar.timegm(time.gmtime())
