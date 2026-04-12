def module_info():
    {
        "who":{

        "name": "EVA test Module",
        "version": "1.0",
        "description": "Test module for EVA AI assistant",
        "author": "Tim",
        "type": "test",

        },

        "life": {
            "status": "active",
            "healthy": 0.3,
            "latency_ms": 20,
            "last_heartbeat": "2024-06-15T12:00:00Z",
            "uptime_hours": 72,
            "error_count": 2,
        },

        "features": {
            "provided_features": [
                "test_feature_1",
                "test_feature_2"
            ],
            "needed_features": [
                "core_integration",
                "logging_support"
            ],
            "permissions": {
                "read_access": True,
                "write_access": False,
                "execute_access": True
            }
        },

        "errors": {
            "last_error": "2024-06-14T15:30:00Z - Minor glitch in test_feature_1",
            "error_log": [
                "2024-06-13T10:00:00Z - Timeout in core_integration",
                "2024-06-14T15:30:00Z - Minor glitch in test_feature_1"
            ],
            "error_severity": {
                "minor": 1,
                "major": 0,
                "critical": 0
            }
        },

        "yui": {
            "yui_allowed": True,
            "yui_status": "monitored", #/ fixing / paused
            "yui_detected_problem": "no",
            "yui_last_action": "2024-06-15T11:45:00Z - System check completed",
            "yui_confidence_level": 0.95
        },

        "control": {
            "enabled": True,
            "can_be_disabled": False,
            "can_be_restarted": True,
            "safety_mode": "active"
        }

}