# CHANGELOG



## v0.1.0 (2023-09-01)

### Chore

* chore: initial commit ([`99c4adb`](https://github.com/frankurcrazy/pybic/commit/99c4adbd6e697d2e8221af37ed1046d27da8afa2))

### Feature

* feat(bic): add support for more bic commands

fix(listener): filter message not meant for the controller

Added support for:
- temperature (r)
- fault_status (r)
- mfr_id (r)
- mfr_model (r)
- mfr_serial (r)
- mfr_date (r)
- mfr_revision (r)
- mfr_location (r) ([`9ce39df`](https://github.com/frankurcrazy/pybic/commit/9ce39dff0fa474f922c4b11eef1d380389d9a4c2))

* feat(bic): impl. bic property getters and setters

feat(listener): impl. CAN listener for bic
feat(utils): impl. can message formatter

Supported Properties:
- operation (r/w)
- v_in (r)
- v_out (r/w)
- i_out (r/w)
- reverse_v_out (r/w)
- reverse_i_out (r/w)
- scaling_factor (r)
- bidirectional_config (r/w)
- system_config (r/w)
- direction_ctrl (r/w) ([`f91c54f`](https://github.com/frankurcrazy/pybic/commit/f91c54f2b2f4b95e1b540d0c8856e390a68c90e4))

### Refactor

* refactor(promise): use promise for asynchronus results ([`c9c8d26`](https://github.com/frankurcrazy/pybic/commit/c9c8d2686dd4f09f1deb78751dac6545ee43b493))

### Style

* style: reformat code with black, isort ([`f1c3c82`](https://github.com/frankurcrazy/pybic/commit/f1c3c8249bbcb3c727b41cbaac09ad6207294682))
