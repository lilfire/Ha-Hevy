# Hevy for Home Assistant

Custom integration for [Hevy](https://www.hevyapp.com/) that uses the full
[Hevy public API v1](https://api.hevyapp.com/docs/): sensors for workouts,
routines and body measurements, plus a service for every API endpoint
(read and write).

> Requires **Hevy Pro** and an API key from
> [hevy.com/settings?developer](https://hevy.com/settings?developer).
> Requires Home Assistant **2025.12.0** or newer.

## Installation

### HACS (custom repository)
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/lilfire/Ha-Hevy`, category *Integration*.
2. Install **Hevy** and restart Home Assistant.

### Manual
Copy `custom_components/hevy` to `<config>/custom_components/hevy` and restart.

### Setup
*Settings → Devices & services → Add integration → Hevy* and paste the API key.
Polling interval (default 15 min, 5–1440) is set under *Configure*.

## Sensors

| Sensor | Description |
|---|---|
| Workouts | Total number of workouts (`/v1/workouts/count`) |
| Last workout | Start time of the latest workout; attributes contain title, exercises, sets, volume, duration |
| Last workout title / duration / volume / sets | Details of the latest workout |
| Workouts this week / last 7 days / last 30 days | Workout counts (week starts Monday, local time) |
| Volume this week | Sum of weight × reps this week |
| Routines / Routine folders | Counts; attributes list id and title |
| Last body measurement | Date of the newest body measurement |
| Weight, Body fat | From the newest body measurement |
| Lean mass + 14 circumferences | Disabled by default; enable in the entity registry |

Hevy does not state the unit of `abdomen`, `waist`, `hips`, `*_thigh` and
`*_calf`; they are assumed to be cm, like the other circumference fields.

On first start the integration downloads the **full workout history** and
caches it locally (`.storage/hevy.<entry_id>`). After that it syncs
incrementally via `/v1/workouts/events`, so restarts and polls only fetch
changes.

## Devices per exercise and per routine

Besides the account device, every exercise you have logged and every routine
in Hevy gets its own device (linked to the account via *via device*), each
with several sensors. New exercises/routines appear automatically; devices for
routines deleted in Hevy are removed.

**Exercise device** (named after the exercise, model = primary muscle group).
Sensors are only created when the exercise has that kind of data:

| Sensor | Default | Notes |
|---|---|---|
| Max weight | on | Heaviest working set; attribute `date` |
| Estimated 1RM | on | Epley: weight × (1 + reps/30), 1 rep = weight; attributes describe the best set |
| Last volume | on | Weight × reps in the latest workout |
| Last performed | on | Timestamp; attributes: template id, type, muscle groups |
| Longest distance / Longest duration | on | Cardio exercises only |
| Best set | off | e.g. `100 kg × 5` |
| Max reps, Workouts, Total sets/reps/volume | off | All-time |
| Last sets / Last reps / Last top weight | off | Latest workout |
| Total distance / Total duration | off | Cardio exercises only |

**Routine device** (model shows the routine folder): Last volume (attributes:
folder, exercises, workout id), Previous volume, Volume change (%), Last
performed, Workouts, Last duration (off by default). Based on workouts started
from the routine.

Warm-up sets are excluded from max weight, 1RM and all volume figures
(including the account-level volume sensors).

### Event: `hevy_new_workout`
Fired when a new workout shows up in Hevy. Data: `config_entry_id`,
`workout_id`, `title`, `start_time`, `end_time`, `duration_minutes`,
`volume_kg`, `set_count`, `exercises`.

```yaml
triggers:
  - trigger: event
    event_type: hevy_new_workout
actions:
  - action: notify.mobile_app_phone
    data:
      message: "Nice! {{ trigger.event.data.title }} – {{ trigger.event.data.volume_kg }} kg"
```

## Services (full API)

Every service takes an optional `config_entry_id`, which is only needed when
more than one Hevy account is configured. `get_*` services return the API
response (`response_variable`). Write services can also return a response and
trigger a sensor refresh.

| Service | Endpoint |
|---|---|
| `hevy.get_user_info` | `GET /v1/user/info` |
| `hevy.get_workouts` | `GET /v1/workouts` |
| `hevy.get_workout` | `GET /v1/workouts/{workoutId}` |
| `hevy.get_workout_count` | `GET /v1/workouts/count` |
| `hevy.get_workout_events` | `GET /v1/workouts/events` |
| `hevy.create_workout` | `POST /v1/workouts` |
| `hevy.update_workout` | `PUT /v1/workouts/{workoutId}` |
| `hevy.get_routines` | `GET /v1/routines` |
| `hevy.get_routine` | `GET /v1/routines/{routineId}` |
| `hevy.create_routine` | `POST /v1/routines` |
| `hevy.update_routine` | `PUT /v1/routines/{routineId}` |
| `hevy.get_routine_folders` | `GET /v1/routine_folders` |
| `hevy.get_routine_folder` | `GET /v1/routine_folders/{folderId}` |
| `hevy.create_routine_folder` | `POST /v1/routine_folders` |
| `hevy.get_exercise_templates` | `GET /v1/exercise_templates` |
| `hevy.get_exercise_template` | `GET /v1/exercise_templates/{exerciseTemplateId}` |
| `hevy.create_exercise_template` | `POST /v1/exercise_templates` |
| `hevy.get_exercise_history` | `GET /v1/exercise_history/{exerciseTemplateId}` |
| `hevy.get_body_measurements` | `GET /v1/body_measurements` |
| `hevy.get_body_measurement` | `GET /v1/body_measurements/{date}` |
| `hevy.create_body_measurement` | `POST /v1/body_measurements` |
| `hevy.update_body_measurement` | `PUT /v1/body_measurements/{date}` |

Times without a time zone are interpreted in Home Assistant's time zone and
sent to Hevy as UTC.

### Examples

Log weight from a smart scale:

```yaml
action: hevy.create_body_measurement
data:
  date: "{{ now().date() }}"
  weight_kg: "{{ states('sensor.scale_weight') | float }}"
```

Fetch history for an exercise:

```yaml
action: hevy.get_exercise_history
data:
  exercise_template_id: D04AC939
  start_date: "2026-01-01 00:00:00"
response_variable: history
```

Log a workout:

```yaml
action: hevy.create_workout
data:
  title: Morning workout
  start_time: "2026-10-03 07:00:00"
  end_time: "2026-10-03 08:00:00"
  is_private: false
  exercises:
    - exercise_template_id: D04AC939
      sets:
        - type: warmup
          weight_kg: 60
          reps: 10
        - weight_kg: 100
          reps: 5
          rpe: 8.5
```

Notes from the API spec:
- `update_workout` and `update_routine` replace the whole object.
- `update_body_measurement` overwrites all fields; fields you leave out are cleared.
- `create_body_measurement` fails with 409 if that date already has a measurement.
- Page size: max 10 (exercise templates: max 100).
- `rpe` accepts 6, 7, 7.5, 8, 8.5, 9, 9.5 or 10.

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
python script/gen_translations.py   # regenerates services.yaml, strings.json, icons.json, translations/
```
