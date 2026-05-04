# engine_v2 Tests

Active test suite for the current redesign path:
- shared timer substrate
- AIR/AIR-O2 semantics
- SURD semantics
- coordinator architecture/seams
- mixed-gas semantics and parity

These tests correspond to:
- `src/dive_stopwatch/engine_v2/`

Current acceptance references:
- [ENGINE_VALIDATION_PROTOCOL.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_VALIDATION_PROTOCOL.md)
- [ENGINE_GOLDEN_PATHS.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_GOLDEN_PATHS.md)
- [test_engine_v2_air_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_air_parity.py)
- [test_engine_v2_mixed_gas_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_mixed_gas_parity.py)
- [test_engine_v2_surd_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_surd_parity.py)

Migration-era redesign/parity tests and obsolete prototype harnesses live under:
- `archive/legacy_redesign/tests/`
