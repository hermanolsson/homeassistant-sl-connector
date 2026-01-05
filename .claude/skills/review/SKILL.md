---
name: review
description: Review Home Assistant integration code against best practices. Use when asked to review code, check quality, or before major releases.
---

# Code Review for Home Assistant Integration

Review the SL Departures integration against Home Assistant and Python best practices.

## Instructions

1. **Fetch Reference Documentation**

   Use WebFetch to get these resources:
   - Home Assistant Integration Quality Scale: https://developers.home-assistant.io/docs/integration_quality_scale_index
   - Config Flow Guide: https://developers.home-assistant.io/docs/config_entries_config_flow_handler
   - DataUpdateCoordinator: https://developers.home-assistant.io/docs/integration_fetching_data
   - Entity Guide: https://developers.home-assistant.io/docs/core/entity

2. **Read All Integration Files**

   - `custom_components/sl_departures/__init__.py`
   - `custom_components/sl_departures/config_flow.py`
   - `custom_components/sl_departures/sensor.py`
   - `custom_components/sl_departures/const.py`
   - `custom_components/sl_departures/manifest.json`
   - `custom_components/sl_departures/strings.json`
   - `custom_components/sl_departures/translations/*.json`

3. **Review Checklist**

   - Config flow follows HA patterns
   - Proper DataUpdateCoordinator usage
   - Correct entity/device registration
   - Complete type hints
   - Correct async patterns (no blocking calls)
   - Appropriate error handling
   - Complete translations
   - Valid manifest.json

4. **Report Findings**

   Format output as:
   - **Critical**: Issues that will cause problems
   - **Warnings**: Potential issues or bad practices
   - **Suggestions**: Nice-to-have improvements
   - **Good**: Things done well (brief)

   Include file paths and line numbers for each finding.
