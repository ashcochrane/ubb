# Around whatever runs the work, where you can act on a stop's scope.
# This is not error handling: the event was recorded and charged.
from ubb import UBBStopRequested

try:
    ...
except UBBStopRequested as stop:
    raise
