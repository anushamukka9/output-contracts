"""Smoke test for the benchmark entry point used by CI."""


def test_benchmark_runs(capsys):
    from output_contracts.benchmark import main

    main()
    out = capsys.readouterr().out
    assert "ops/sec" in out
    assert "benchmark smoke test passed" in out
