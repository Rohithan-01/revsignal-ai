import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

with patch.dict(
    os.environ,
    {"DATABASE_URL": "postgresql+asyncpg://localhost/revsignal_test"},
):
    from app.main import app, register_seed_endpoint
from app.models import Base


class SeedEndpointRegistrationTests(unittest.TestCase):
    def test_seed_endpoint_is_not_registered_by_default(self):
        test_app = FastAPI()

        with patch.dict(os.environ, {}, clear=True):
            register_seed_endpoint(test_app)

        self.assertNotIn(
            "/seed/deals",
            {route.path for route in test_app.routes},
        )

    def test_seed_endpoint_is_registered_when_explicitly_enabled(self):
        test_app = FastAPI()

        with patch.dict(
            os.environ,
            {"ENABLE_SEED_ENDPOINT": "true"},
            clear=True,
        ):
            register_seed_endpoint(test_app)

        self.assertIn(
            "/seed/deals",
            {route.path for route in test_app.routes},
        )


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
        expected_close_date = datetime.now(timezone.utc) + timedelta(days=10)
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

    async def test_sqlalchemy_failure_returns_service_unavailable(self):
        class FailingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                raise SQLAlchemyError("simulated database failure")

        with patch("app.main.SessionLocal", FailingSession):
            response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Database is temporarily unavailable"},
        )


if __name__ == "__main__":
    unittest.main()
