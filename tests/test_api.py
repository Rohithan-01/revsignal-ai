import importlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.engine import activity_engine, risk_engine

with patch.dict(
    os.environ,
    {"DATABASE_URL": "postgresql+asyncpg://localhost/revsignal_test"},
):
    import app.main as main_module

    app = main_module.app
from app.models import Activity, Base


class SeedEndpointRegistrationTests(unittest.TestCase):
    def test_seed_endpoint_is_not_registered_by_default(self):
        original_app = main_module.app
        with patch.dict(os.environ):
            try:
                os.environ.pop("ENABLE_SEED_ENDPOINT", None)
                configured_app = importlib.reload(main_module).app
                seed_routes = [
                    route
                    for route in configured_app.routes
                    if route.path == "/seed/deals"
                ]
                self.assertEqual(seed_routes, [])
            finally:
                main_module.app = original_app

    def test_seed_endpoint_is_registered_when_explicitly_enabled(self):
        original_app = main_module.app
        with patch.dict(os.environ):
            try:
                os.environ["ENABLE_SEED_ENDPOINT"] = "true"
                configured_app = importlib.reload(main_module).app
                seed_routes = [
                    route
                    for route in configured_app.routes
                    if route.path == "/seed/deals"
                ]
                self.assertEqual(len(seed_routes), 1)
                self.assertEqual(seed_routes[0].methods, {"POST"})
            finally:
                main_module.app = original_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.session_patcher = patch(
            "app.main.SessionLocal",
            self.session_factory,
        )
        self.session_patcher.start()
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.session_patcher.stop()
        await self.engine.dispose()

    async def create_deal(self, **overrides):
        deal = {
            "company": "Acme Corp",
            "deal_value": 50000,
            "stage": "Negotiation",
            "probability": 70,
        }
        deal.update(overrides)
        response = await self.client.post("/deals", json=deal)
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_import_csv_creates_all_three_deals(self):
        csv_content = (
            "company,deal_value,stage,probability,expected_close_date\n"
            "Zenith Technologies,65000,Negotiation,25,2026-11-10\n"
            "BlueWave Solutions,95000,Proposal,75,2026-11-18\n"
            "PixelCore Systems,40000,Qualified,45,\n"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("deals.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["count"], 3)
        self.assertEqual(
            [deal["company"] for deal in result["deals"]],
            ["Zenith Technologies", "BlueWave Solutions", "PixelCore Systems"],
        )
        self.assertEqual(
            result["deals"][0]["expected_close_date"],
            "2026-11-10",
        )
        self.assertIsNone(result["deals"][2]["expected_close_date"])
        self.assertIn("risk_level", result["deals"][0])
        self.assertIn("recommendation", result["deals"][0])
        retrieved = await self.client.get("/deals")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(
            retrieved.json()[0]["expected_close_date"],
            "2026-11-10",
        )

    async def test_import_csv_invalid_row_does_not_insert_partial_deals(self):
        csv_content = (
            "company,deal_value,stage,probability,expected_close_date\n"
            "Valid Deal,10000,Qualified,50,2026-11-10\n"
            "Invalid Deal,20000,Proposal,101,2026-11-20\n"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("deals.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("row 3, probability", response.text)
        deals = await self.client.get("/deals")
        self.assertEqual(deals.status_code, 200)
        self.assertEqual(deals.json(), [])

    async def test_import_csv_rejects_missing_headers(self):
        csv_content = (
            "company,deal_value,stage,probability\n"
            "Acme,10000,Qualified,50\n"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("deals.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("row 1", response.text)
        self.assertIn("expected_close_date", response.text)
        deals = await self.client.get("/deals")
        self.assertEqual(deals.json(), [])

    async def test_import_csv_rejects_malformed_input(self):
        csv_content = (
            "company,deal_value,stage,probability,expected_close_date\n"
            'Acme,10000,Qualified,50,"2026-11-10\n'
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("deals.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Malformed CSV near row", response.json()["detail"])
        deals = await self.client.get("/deals")
        self.assertEqual(deals.json(), [])

    async def test_create_and_retrieve_deal_includes_risk_signals(self):
        created = await self.create_deal(probability=20)

        self.assertEqual(created["overall_risk_level"], "HIGH")
        self.assertEqual(
            created["risk_reasons"],
            [
                "Low closing probability",
                "Expected close date is not set",
                "No customer activity recorded",
            ],
        )
        self.assertEqual(
            created["recommendation"],
            "Closely monitor and follow up",
        )

        response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], created["id"])
        self.assertEqual(response.json()[0]["risk_reasons"], created["risk_reasons"])

    async def test_get_deal_includes_activities_and_latest_activity_date(self):
        deal = await self.create_deal()
        older_date = datetime.now(timezone.utc) - timedelta(days=2)
        latest_date = datetime.now(timezone.utc)

        for activity_date, activity_type in (
            (older_date, "Email"),
            (latest_date, "Call"),
        ):
            response = await self.client.post(
                "/activities",
                json={
                    "deal_id": deal["id"],
                    "activity_type": activity_type,
                    "activity_date": activity_date.isoformat(),
                },
            )
            self.assertEqual(response.status_code, 200)

        response = await self.client.get(f"/deals/{deal['id']}")
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["id"], deal["id"])
        self.assertEqual(detail["activity_status"], "ACTIVE")
        self.assertEqual(
            datetime.fromisoformat(
                detail["latest_activity_date"]
            ).replace(tzinfo=timezone.utc),
            latest_date,
        )
        self.assertEqual(
            {activity["activity_type"] for activity in detail["activities"]},
            {"Email", "Call"},
        )
        self.assertEqual(len(detail["activities"]), 2)

    async def test_get_deal_without_activities_has_empty_activity_details(self):
        deal = await self.create_deal()

        response = await self.client.get(f"/deals/{deal['id']}")

        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertIsNone(detail["latest_activity_date"])
        self.assertEqual(detail["activities"], [])
        self.assertEqual(detail["activity_status"], "NO_ACTIVITY")
        self.assertIsNone(detail["days_since_last_activity"])

    async def test_get_nonexistent_deal_returns_not_found(self):
        response = await self.client.get("/deals/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Deal not found"})

    async def test_get_deal_returns_current_risk_and_recommendation(self):
        expected_close_date = (
            datetime.now(timezone.utc) + timedelta(days=10)
        ).date()
        deal = await self.create_deal(
            probability=20,
            expected_close_date=expected_close_date.isoformat(),
        )
        await self.client.post(
            "/activities",
            json={
                "deal_id": deal["id"],
                "activity_type": "Call",
                "activity_date": datetime.now(timezone.utc).isoformat(),
            },
        )

        response = await self.client.get(f"/deals/{deal['id']}")

        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["risk_level"], "HIGH")
        self.assertEqual(detail["overall_risk_level"], "MEDIUM")
        self.assertEqual(detail["risk_reasons"], ["Low closing probability"])
        self.assertFalse(detail["is_overdue"])
        self.assertEqual(detail["recommendation"], "Schedule a follow-up")

    async def test_create_and_retrieve_activity_and_signal(self):
        deal = await self.create_deal()
        activity_date = datetime.now(timezone.utc).isoformat()

        created = await self.client.post(
            "/activities",
            json={
                "deal_id": deal["id"],
                "activity_type": "Call",
                "activity_date": activity_date,
                "notes": "Discussed next steps",
            },
        )
        self.assertEqual(created.status_code, 200)
        activity_id = created.json()["id"]

        all_activities = await self.client.get("/activities")
        deal_activities = await self.client.get(
            f"/deals/{deal['id']}/activities"
        )
        signal = await self.client.get(
            f"/deals/{deal['id']}/activity-signal"
        )

        self.assertEqual(all_activities.status_code, 200)
        self.assertEqual(deal_activities.status_code, 200)
        self.assertEqual(all_activities.json()[0]["id"], activity_id)
        self.assertEqual(deal_activities.json()[0]["activity_type"], "Call")
        self.assertEqual(signal.status_code, 200)
        self.assertEqual(signal.json()["activity_status"], "ACTIVE")
        self.assertEqual(signal.json()["days_since_last_activity"], 0)

        deals = await self.client.get("/deals")
        self.assertEqual(deals.json()[0]["activity_status"], "ACTIVE")
        self.assertEqual(deals.json()[0]["days_since_last_activity"], 0)

    async def test_stale_activity_is_reported_by_signal_endpoint(self):
        deal = await self.create_deal()
        activity_date = datetime.now(timezone.utc) - timedelta(days=5)

        created = await self.client.post(
            "/activities",
            json={
                "deal_id": deal["id"],
                "activity_type": "Call",
                "activity_date": activity_date.isoformat(),
            },
        )
        self.assertEqual(created.status_code, 200)

        signal = await self.client.get(
            f"/deals/{deal['id']}/activity-signal"
        )

        self.assertEqual(signal.status_code, 200)
        self.assertEqual(signal.json()["days_since_last_activity"], 5)
        self.assertEqual(signal.json()["activity_status"], "STALE")

    async def test_get_deals_handles_historical_future_activity_without_error(self):
        deal = await self.create_deal()
        fixed_now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        future_activity = fixed_now + timedelta(hours=2)

        async with self.session_factory() as session:
            session.add(
                Activity(
                    deal_id=deal["id"],
                    activity_type="Call",
                    activity_date=future_activity,
                )
            )
            await session.commit()

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return fixed_now.replace(tzinfo=None)
                return fixed_now.astimezone(tz)

        client = AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        )
        try:
            with patch.object(activity_engine, "datetime", FixedDateTime):
                response = await client.get("/deals")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[0]["days_since_last_activity"])
        self.assertEqual(response.json()[0]["activity_status"], "NO_ACTIVITY")

    async def test_end_to_end_deal_activity_assessment_workflow(self):
        fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return fixed_now.replace(tzinfo=None)
                return fixed_now.astimezone(tz)

        expected_close_date = (fixed_now - timedelta(days=1)).date()
        activity_date = fixed_now - timedelta(days=5)

        with (
            patch.object(activity_engine, "datetime", FixedDateTime),
            patch.object(risk_engine, "datetime", FixedDateTime),
        ):
            created_deal = await self.client.post(
                "/deals",
                json={
                    "company": "Acme Corp",
                    "deal_value": 50000,
                    "stage": "Negotiation",
                    "probability": 20,
                    "expected_close_date": expected_close_date.isoformat(),
                },
            )
            self.assertEqual(created_deal.status_code, 200)
            deal = created_deal.json()

            created_activity = await self.client.post(
                "/activities",
                json={
                    "deal_id": deal["id"],
                    "activity_type": "Call",
                    "activity_date": activity_date.isoformat(),
                    "notes": "Discussed next steps",
                },
            )
            self.assertEqual(created_activity.status_code, 200)
            activity = created_activity.json()

            all_activities = await self.client.get("/activities")
            deal_activities = await self.client.get(
                f"/deals/{deal['id']}/activities"
            )
            signal = await self.client.get(
                f"/deals/{deal['id']}/activity-signal"
            )
            deal_detail = await self.client.get(f"/deals/{deal['id']}")

        self.assertEqual(activity["deal_id"], deal["id"])
        self.assertEqual(activity["activity_type"], "Call")
        self.assertEqual(activity["notes"], "Discussed next steps")
        self.assertEqual(all_activities.status_code, 200)
        self.assertEqual(len(all_activities.json()), 1)
        self.assertEqual(all_activities.json()[0]["id"], activity["id"])
        self.assertEqual(deal_activities.status_code, 200)
        self.assertEqual(len(deal_activities.json()), 1)
        self.assertEqual(deal_activities.json()[0]["id"], activity["id"])
        self.assertEqual(
            datetime.fromisoformat(
                deal_activities.json()[0]["activity_date"]
            ).replace(tzinfo=timezone.utc),
            activity_date,
        )
        self.assertEqual(
            signal.json(),
            {
                "deal_id": deal["id"],
                "days_since_last_activity": 5,
                "activity_status": "STALE",
            },
        )
        self.assertEqual(deal_detail.status_code, 200)
        detail = deal_detail.json()
        self.assertEqual(detail["id"], deal["id"])
        self.assertEqual(len(detail["activities"]), 1)
        self.assertEqual(detail["activities"][0]["id"], activity["id"])
        self.assertEqual(detail["risk_level"], "HIGH")
        self.assertEqual(detail["overall_risk_level"], "HIGH")
        self.assertEqual(
            detail["risk_reasons"],
            [
                "Low closing probability",
                "Expected close date has passed",
                "Customer activity is stale",
            ],
        )
        self.assertTrue(detail["is_overdue"])
        self.assertEqual(detail["activity_status"], "STALE")
        self.assertEqual(detail["days_since_last_activity"], 5)
        self.assertEqual(detail["recommendation"], "Review deal immediately")

    async def test_activity_validation_accepts_boundaries_and_optional_notes(self):
        deal = await self.create_deal()
        payload = {
            "deal_id": deal["id"],
            "activity_type": "T" * 50,
            "activity_date": datetime.now(timezone.utc).isoformat(),
            "notes": "N" * 500,
        }

        boundary_response = await self.client.post("/activities", json=payload)
        optional_notes_response = await self.client.post(
            "/activities",
            json={
                "deal_id": deal["id"],
                "activity_type": "Call",
                "activity_date": datetime.now(timezone.utc).isoformat(),
            },
        )

        self.assertEqual(boundary_response.status_code, 200)
        self.assertEqual(boundary_response.json()["activity_type"], "T" * 50)
        self.assertEqual(boundary_response.json()["notes"], "N" * 500)
        self.assertEqual(optional_notes_response.status_code, 200)
        self.assertIsNone(optional_notes_response.json()["notes"])

    async def test_invalid_activity_fields_are_rejected_without_database_access(self):
        invalid_fields = (
            ("activity_type", " \t\n"),
            ("activity_type", "T" * 51),
            ("notes", "N" * 501),
        )

        for field, value in invalid_fields:
            with self.subTest(field=field, value_length=len(value)):
                payload = {
                    "deal_id": 1,
                    "activity_type": "Call",
                    "activity_date": datetime.now(timezone.utc).isoformat(),
                    field: value,
                }
                with patch("app.main.SessionLocal") as session_local:
                    response = await self.client.post(
                        "/activities",
                        json=payload,
                    )

                self.assertEqual(response.status_code, 422)
                session_local.assert_not_called()

    async def test_activity_api_normalizes_offsets_and_rejects_naive_or_far_future(self):
        deal = await self.create_deal()
        now = datetime.now(timezone.utc)
        within_tolerance = (now + timedelta(minutes=4)).astimezone(
            timezone(timedelta(hours=5, minutes=30))
        )

        accepted = await self.client.post(
            "/activities",
            json={
                "deal_id": deal["id"],
                "activity_type": "Call",
                "activity_date": within_tolerance.isoformat(),
            },
        )

        self.assertEqual(accepted.status_code, 200)
        returned_date = datetime.fromisoformat(
            accepted.json()["activity_date"]
        )
        self.assertEqual(returned_date.utcoffset(), timedelta(0))
        self.assertEqual(
            returned_date.astimezone(timezone.utc),
            within_tolerance.astimezone(timezone.utc),
        )

        for activity_date in (
            (now + timedelta(minutes=6)).isoformat(),
            (now + timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
        ):
            with self.subTest(activity_date=activity_date):
                with patch("app.main.SessionLocal") as session_local:
                    response = await self.client.post(
                        "/activities",
                        json={
                            "deal_id": deal["id"],
                            "activity_type": "Call",
                            "activity_date": activity_date,
                        },
                    )

                self.assertEqual(response.status_code, 422)
                session_local.assert_not_called()

    async def test_invalid_probability_is_rejected(self):
        response = await self.client.post(
            "/deals",
            json={
                "company": "Acme Corp",
                "deal_value": 50000,
                "stage": "Negotiation",
                "probability": 101,
            },
        )

        self.assertEqual(response.status_code, 422)

    async def test_deal_close_date_must_be_calendar_date_only(self):
        with patch("app.main.SessionLocal") as session_local:
            response = await self.client.post(
                "/deals",
                json={
                    "company": "Acme Corp",
                    "deal_value": 50000,
                    "stage": "Negotiation",
                    "probability": 70,
                    "expected_close_date": "2026-11-10T00:00:00Z",
                },
            )

        self.assertEqual(response.status_code, 422)
        session_local.assert_not_called()

    async def test_deal_validation_accepts_inclusive_boundaries(self):
        response = await self.client.post(
            "/deals",
            json={
                "company": "C" * 255,
                "deal_value": 0,
                "stage": "S" * 100,
                "probability": 100,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["company"], "C" * 255)
        self.assertEqual(response.json()["deal_value"], 0)
        self.assertEqual(response.json()["stage"], "S" * 100)
        self.assertEqual(response.json()["probability"], 100)

    async def test_invalid_deal_text_is_rejected_without_database_access(self):
        invalid_fields = (
            ("company", " \t\n"),
            ("company", "C" * 256),
            ("stage", " \t\n"),
            ("stage", "S" * 101),
        )

        for field, value in invalid_fields:
            with self.subTest(field=field, value_length=len(value)):
                payload = {
                    "company": "Acme Corp",
                    "deal_value": 50000,
                    "stage": "Negotiation",
                    "probability": 70,
                    field: value,
                }
                with patch("app.main.SessionLocal") as session_local:
                    response = await self.client.post("/deals", json=payload)

                self.assertEqual(response.status_code, 422)
                session_local.assert_not_called()

    async def test_invalid_deal_values_are_rejected_without_database_access(self):
        for deal_value in (-0.01, float("nan"), float("inf"), float("-inf")):
            with self.subTest(deal_value=deal_value):
                payload = {
                    "company": "Acme Corp",
                    "deal_value": deal_value,
                    "stage": "Negotiation",
                    "probability": 70,
                }
                with patch("app.main.SessionLocal") as session_local:
                    response = await self.client.post(
                        "/deals",
                        content=json.dumps(payload, allow_nan=True),
                        headers={"content-type": "application/json"},
                    )

                self.assertEqual(response.status_code, 422)
                session_local.assert_not_called()

    async def test_missing_deal_returns_not_found(self):
        missing_id = 999

        activities = await self.client.get(
            f"/deals/{missing_id}/activities"
        )
        signal = await self.client.get(
            f"/deals/{missing_id}/activity-signal"
        )
        create_activity = await self.client.post(
            "/activities",
            json={
                "deal_id": missing_id,
                "activity_type": "Call",
                "activity_date": datetime.now(timezone.utc).isoformat(),
            },
        )

        self.assertEqual(activities.status_code, 404)
        self.assertEqual(signal.status_code, 404)
        self.assertEqual(create_activity.status_code, 404)
        self.assertEqual(
            create_activity.json(),
            {"detail": "Deal not found"},
        )

    async def test_unclassified_sqlalchemy_failure_returns_internal_error(self):
        class FailingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                raise SQLAlchemyError("simulated database failure")

        with patch("app.main.SessionLocal", FailingSession):
            response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"detail": "Database operation failed"},
        )

    async def test_invalidated_database_connection_returns_service_unavailable(self):
        class FailingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                raise OperationalError(
                    "SELECT sensitive_sql",
                    {},
                    Exception("sensitive connection details"),
                    connection_invalidated=True,
                )

        with patch("app.main.SessionLocal", FailingSession):
            response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Database is temporarily unavailable"},
        )
        self.assertNotIn("sensitive_sql", response.text)
        self.assertNotIn("sensitive connection details", response.text)

    async def test_integrity_failure_during_activity_write_returns_conflict(self):
        class FailingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def get(self, model, deal_id):
                return main_module.Deal(
                    id=deal_id,
                    company="Acme Corp",
                    deal_value=50000,
                    stage="Negotiation",
                    probability=70,
                )

            def add(self, instance):
                pass

            async def commit(self):
                raise IntegrityError(
                    "INSERT INTO activities",
                    {},
                    Exception("sensitive constraint details"),
                )

        with patch("app.main.SessionLocal", FailingSession):
            response = await self.client.post(
                "/activities",
                json={
                    "deal_id": 1,
                    "activity_type": "Call",
                    "activity_date": datetime.now(timezone.utc).isoformat(),
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": "Database constraint violation"},
        )
        self.assertNotIn("INSERT INTO", response.text)
        self.assertNotIn("sensitive constraint details", response.text)


if __name__ == "__main__":
    unittest.main()
