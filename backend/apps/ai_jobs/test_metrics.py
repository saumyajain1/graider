import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from config.ai_metrics import container_resources, metric, provider_timing


class ExecutionMetricsTests(SimpleTestCase):
    @override_settings(GRAIDER_AI_METRICS=False)
    @patch("config.ai_metrics.container_resources")
    @patch("config.ai_metrics.logger")
    def test_disabled_metrics_do_no_resource_reads(self, logger, resources):
        with provider_timing(1, "submission_grading", "test-model"):
            pass
        metric("results_committed", job_id="test-job")
        resources.assert_not_called()
        logger.info.assert_not_called()

    @override_settings(GRAIDER_AI_METRICS=True)
    @patch("config.ai_metrics.container_resources", return_value={"memory_bytes": 42})
    @patch("config.ai_metrics.logger")
    def test_failed_call_records_timing_without_exception_content(self, logger, resources):
        with self.assertRaisesRegex(RuntimeError, "private prompt"):
            with provider_timing(1, "submission_grading", "test-model"):
                raise RuntimeError("private prompt and API credential")
        events = [json.loads(call.args[1]) for call in logger.info.call_args_list]
        self.assertEqual([row["event"] for row in events], ["provider_start", "provider_end"])
        self.assertEqual(events[-1]["outcome"], "error")
        self.assertGreaterEqual(events[-1]["duration_seconds"], 0)
        self.assertNotIn("private", json.dumps(events))

    @patch("config.ai_metrics.Path.read_text", side_effect=OSError)
    def test_resource_sampling_is_optional(self, read):
        self.assertEqual(container_resources(), {})

    @patch("config.ai_metrics.Path.exists", return_value=True)
    @patch("config.ai_metrics.Path.read_text")
    def test_cgroup_v2_units(self, read, exists):
        read.side_effect = ["1048576", "usage_usec 2000000\nuser_usec 1000000", "oom_kill 0"]
        self.assertEqual(
            container_resources(), {"memory_bytes": 1048576, "cpu_seconds": 2, "oom_kills": 0}
        )
