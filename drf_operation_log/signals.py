from django import dispatch

operation_logs_pre_save = dispatch.Signal(providing_args=["request", "operation_logs"])
