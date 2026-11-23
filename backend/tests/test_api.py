import asyncio
import importlib
import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.engine import activity_engine, risk_engine

with patch.dict(
    os.environ,
    {"DATABASE_URL": "postgresql+asyncpg://localhost/revsignal_test"},
):
    import backend.app.main as main_module

    app = main_module.app
from backend.app.models import Activity, Base, Deal


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
            "backend.app.main.SessionLocal",
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

    async def test_creation_distinguishes_omitted_and_explicit_probability(self):
        unknown = await self.client.post(
            "/deals",
            json={
                "company": "Unknown Probability",
                "deal_value": 50000,
                "stage": "Proposal",
            },
        )
        explicit_default = await self.client.post(
            "/deals",
            json={
                "company": "Explicit Probability",
                "deal_value": 50000,
                "stage": "Proposal",
                "probability": 50,
            },
        )

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(explicit_default.status_code, 200)
        self.assertEqual(unknown.json()["probability"], 50)
        self.assertFalse(unknown.json()["probability_is_known"])
        self.assertEqual(explicit_default.json()["probability"], 50)
        self.assertTrue(explicit_default.json()["probability_is_known"])

        listed = await self.client.get("/api/deals")
        known_by_company = {
            deal["account_name"]: deal["probability_is_known"]
            for deal in listed.json()
        }
        self.assertFalse(known_by_company["Unknown Probability"])
        self.assertTrue(known_by_company["Explicit Probability"])

    async def test_new_deal_ids_start_at_101_and_increase_sequentially(self):
        await self.create_deal(company="First Generated Deal")
        await self.create_deal(company="Second Generated Deal")
        listed = await self.client.get("/api/deals")

        deal_ids_by_company = {
            deal["account_name"]: deal["deal_id"]
            for deal in listed.json()
        }
        self.assertEqual(deal_ids_by_company["First Generated Deal"], "D-101")
        self.assertEqual(deal_ids_by_company["Second Generated Deal"], "D-102")

    async def test_concurrent_deal_creation_allocates_distinct_ids(self):
        responses = await asyncio.gather(
            *(
                self.client.post(
                    "/deals",
                    json={
                        "company": f"Concurrent Deal {index}",
                        "deal_value": 50000,
                        "stage": "Proposal",
                    },
                )
                for index in range(2)
            )
        )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        listed = await self.client.get("/api/deals")
        self.assertEqual(
            {deal["deal_id"] for deal in listed.json()},
            {"D-101", "D-102"},
        )

    async def test_optional_seed_endpoint_rejects_repeated_ids(self):
        first = await main_module.seed_deals()

        self.assertEqual(first["count"], 5)
        with self.assertRaises(main_module.HTTPException) as duplicate:
            await main_module.seed_deals()
        self.assertEqual(duplicate.exception.status_code, 409)
        deals = await self.client.get("/api/deals")
        self.assertEqual(len(deals.json()), 5)
        self.assertEqual(
            {deal["deal_id"] for deal in deals.json()},
            {f"D-{number}" for number in range(113, 118)},
        )

    async def test_crm_csv_without_probability_stays_unknown_with_numeric_default(self):
        upload = await self.client.post(
            "/api/deals/upload",
            files={
                "file": (
                    "crm.csv",
                    (
                        "deal_id,account_name,deal_value,stage,status\n"
                        "D-901,Unknown Probability,50000,Proposal,open\n"
                    ),
                    "text/csv",
                )
            },
        )

        self.assertEqual(upload.status_code, 200)
        listed = await self.client.get("/api/deals")
        crm_deal = next(
            deal for deal in listed.json()
            if deal["deal_id"] == "D-901"
        )
        self.assertEqual(crm_deal["probability"], 50)
        self.assertFalse(crm_deal["probability_is_known"])

    async def test_analysis_and_crm_endpoints_share_known_probability_assessment(self):
        async with self.session_factory() as session:
            deal = Deal(
                deal_id="D-902",
                company="Known Probability Account",
                deal_value=50000,
                stage="Proposal",
                status="open",
                probability=25,
                probability_is_known=True,
                created_date=date.today(),
                expected_close_date=date.today() + timedelta(days=60),
                last_activity_date=date.today(),
                activity_count=5,
                meeting_count=2,
                email_count=5,
                stakeholder_count=3,
            )
            session.add(deal)
            await session.commit()

        analyzed = await self.client.post(
            "/api/deals/D-902/analyze"
        )
        listed = await self.client.get("/api/deals/D-902")
        all_deals = await self.client.get("/api/deals")
        high_risk = await self.client.get("/api/deals/high-risk")
        metrics = await self.client.get("/api/metrics")

        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(all_deals.status_code, 200)
        self.assertEqual(high_risk.status_code, 200)
        self.assertEqual(metrics.status_code, 200)
        responses = [
            analyzed.json(),
            listed.json(),
            next(
                deal for deal in all_deals.json()
                if deal["deal_id"] == "D-902"
            ),
            next(
                deal for deal in high_risk.json()
                if deal["deal_id"] == "D-902"
            ),
            next(
                deal for deal in metrics.json()["top_deals"]
                if deal["deal_id"] == "D-902"
            ),
        ]
        for response in responses:
            self.assertEqual(response["risk_level"], "HIGH")
            self.assertTrue(response["probability_is_known"])
            self.assertIn(
                "Closing probability is 25%, raising risk to HIGH.",
                response["risk_reasons"],
            )
        self.assertEqual(
            {response["recommended_action"] for response in responses},
            {responses[0]["recommended_action"]},
        )

        async with self.session_factory() as session:
            stored = await session.get(Deal, deal.id)
            self.assertEqual(stored.probability, 25)
            self.assertTrue(stored.probability_is_known)
            self.assertEqual(stored.risk_level, "HIGH")

    async def test_unknown_probability_medium_risk_is_consistent_across_crm_endpoints(self):
        async with self.session_factory() as session:
            deal = Deal(
                deal_id="D-903",
                company="Unknown Probability Account",
                deal_value=50000,
                stage="Proposal",
                status="open",
                probability=25,
                probability_is_known=False,
                created_date=date.today(),
                expected_close_date=date.today() + timedelta(days=60),
                last_activity_date=None,
                activity_count=1,
                meeting_count=2,
                email_count=5,
                stakeholder_count=1,
            )
            session.add(deal)
            await session.commit()

        analyzed = await self.client.post(
            "/api/deals/D-903/analyze"
        )
        listed = await self.client.get("/api/deals")
        medium_risk = await self.client.get(
            "/api/deals",
            params={"risk_level": "MEDIUM"},
        )
        high_filter = await self.client.get(
            "/api/deals",
            params={"risk_level": "HIGH"},
        )
        high_risk = await self.client.get("/api/deals/high-risk")
        metrics = await self.client.get("/api/metrics")

        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(medium_risk.status_code, 200)
        self.assertEqual(high_filter.status_code, 200)
        self.assertEqual(high_risk.status_code, 200)
        self.assertEqual(metrics.status_code, 200)

        deal_responses = [
            analyzed.json(),
            next(
                item for item in listed.json()
                if item["deal_id"] == "D-903"
            ),
            medium_risk.json()[0],
            next(
                item for item in metrics.json()["top_deals"]
                if item["deal_id"] == "D-903"
            ),
        ]
        for response in deal_responses:
            self.assertEqual(response["risk_score"], 44)
            self.assertEqual(response["risk_level"], "MEDIUM")
            self.assertEqual(response["probability"], 25)
            self.assertFalse(response["probability_is_known"])
        self.assertFalse(
            any(
                "probability" in reason.lower()
                for reason in deal_responses[0]["risk_reasons"]
            )
        )
        self.assertNotIn(
            "D-903",
            [item["deal_id"] for item in high_filter.json()],
        )
        self.assertNotIn(
            "D-903",
            [item["deal_id"] for item in high_risk.json()],
        )
        self.assertEqual(metrics.json()["high_risk_deals"], 0)
        self.assertEqual(
            metrics.json()["deal_distribution_by_risk"],
            {"LOW": 0, "MEDIUM": 1, "HIGH": 0},
        )

    async def test_analysis_uses_related_activity_when_crm_date_is_missing(self):
        async with self.session_factory() as session:
            deal = Deal(
                deal_id="D-904",
                company="Activity Date Account",
                deal_value=50000,
                stage="Proposal",
                status="open",
                probability=75,
                probability_is_known=True,
                created_date=date.today(),
                expected_close_date=date.today() + timedelta(days=60),
            )
            session.add(deal)
            await session.flush()
            session.add(
                Activity(
                    deal_id=deal.id,
                    activity_type="Call",
                    activity_date=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        before_analysis = await self.client.get(
            "/api/deals/D-904"
        )
        analyzed = await self.client.post(
            "/api/deals/D-904/analyze"
        )

        self.assertEqual(before_analysis.status_code, 200)
        self.assertEqual(analyzed.status_code, 200)
        self.assertFalse(
            any(
                "activity was provided" in reason.lower()
                for reason in analyzed.json()["risk_reasons"]
            )
        )
        self.assertEqual(
            analyzed.json()["risk_reasons"],
            before_analysis.json()["risk_reasons"],
        )

    async def test_seed_upsert_does_not_replace_known_probability_with_unknown(self):
        async with self.session_factory() as session:
            deal = Deal(
                deal_id="D-905",
                company="Existing Account",
                deal_value=50000,
                stage="Proposal",
                status="open",
                probability=40,
                probability_is_known=True,
            )
            session.add(deal)
            await session.commit()

            assessment = main_module.analyze_deal(
                {
                    "deal_id": "D-905",
                    "account_name": "Updated Account",
                    "deal_value": 60000,
                    "stage": "Negotiation",
                    "status": "open",
                }
            )
            await main_module._upsert_deal(session, assessment)
            await session.commit()
            await session.refresh(deal)

            self.assertEqual(deal.probability, 40)
            self.assertTrue(deal.probability_is_known)
            self.assertEqual(deal.account_name, "Updated Account")

    async def test_database_health_returns_healthy_when_select_succeeds(self):
        class FakeConnection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                self.statement = statement

        connection = FakeConnection()

        class FakeEngine:
            def connect(self):
                return connection

        with patch(
            "backend.app.main.engine",
            FakeEngine(),
        ):
            response = await self.client.get("/health/db")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "healthy", "database": "connected"},
        )
        self.assertEqual(str(connection.statement), "SELECT 1")

    async def test_database_health_returns_unhealthy_when_query_fails(self):
        class FailingConnection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                raise SQLAlchemyError("sensitive database failure")

        class FakeEngine:
            def connect(self):
                return FailingConnection()

        with patch(
            "backend.app.main.engine",
            FakeEngine(),
        ), self.assertLogs("uvicorn.error", level="ERROR") as captured:
            response = await self.client.get("/health/db")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unhealthy", "database": "disconnected"},
        )
        self.assertNotIn("sensitive database failure", response.text)
        self.assertIn(
            "GET /health/db",
            "\n".join(captured.output),
        )

    async def test_get_deals_returns_empty_list_for_empty_database(self):
        response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    async def test_sample_deals_csv_import_preserves_legacy_contract(self):
        sample_file = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "sample_deals.csv"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={
                "file": (
                    sample_file.name,
                    sample_file.read_bytes(),
                    "text/csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 3)
        self.assertEqual(
            [deal["company"] for deal in response.json()["deals"]],
            ["Zenith Technologies", "BlueWave Solutions", "PixelCore Systems"],
        )
        retrieved = await self.client.get("/deals")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(len(retrieved.json()), 3)
        self.assertTrue(
            all(deal["probability_is_known"] for deal in retrieved.json())
        )
        deals_by_company = {
            deal["company"]: deal
            for deal in retrieved.json()
        }
        self.assertEqual(
            deals_by_company["BlueWave Solutions"]["risk_level"],
            "LOW",
        )
        self.assertEqual(
            deals_by_company["BlueWave Solutions"]["overall_risk_level"],
            "MEDIUM",
        )
        crm_deals = await self.client.get("/api/deals")
        self.assertEqual(
            {
                deal["account_name"]: deal["deal_id"]
                for deal in crm_deals.json()
            },
            {
                "Zenith Technologies": "D-102",
                "BlueWave Solutions": "D-103",
                "PixelCore Systems": "D-104",
            },
        )

        repeated = await self.client.post(
            "/deals/import-csv",
            files={
                "file": (
                    sample_file.name,
                    sample_file.read_bytes(),
                    "text/csv",
                )
            },
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(
            repeated.json()["detail"]["deal_ids"],
            ["D-102", "D-103", "D-104"],
        )
        after_repeat = await self.client.get("/deals")
        self.assertEqual(len(after_repeat.json()), 3)

    async def test_sample_crm_csv_import_preserves_crm_contract(self):
        sample_file = (
            Path(__file__).resolve().parents[2] / "data" / "sample_crm.csv"
        )

        response = await self.client.post(
            "/api/deals/upload",
            files={
                "file": (
                    sample_file.name,
                    sample_file.read_bytes(),
                    "text/csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records_imported"], 8)
        retrieved = await self.client.get("/api/deals")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(len(retrieved.json()), 8)
        self.assertIn(
            "D-105",
            {deal["deal_id"] for deal in retrieved.json()},
        )
        self.assertEqual(
            {deal["deal_id"] for deal in retrieved.json()},
            {f"D-{number}" for number in range(105, 113)},
        )

    async def test_sample_crm_seed_is_repeatable_without_duplicate_deals(self):
        first = await self.client.get("/seed/sample")
        second = await self.client.get("/seed/sample")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["records_imported"], 8)
        self.assertEqual(second.json()["records_imported"], 8)
        deals = await self.client.get("/api/deals")
        self.assertEqual(len(deals.json()), 8)
        self.assertEqual(
            {deal["deal_id"] for deal in deals.json()},
            {f"D-{number}" for number in range(105, 113)},
        )
        await self.create_deal(company="First Deal After CRM Seed")
        listed_after_create = await self.client.get("/api/deals")
        generated = next(
            deal for deal in listed_after_create.json()
            if deal["account_name"] == "First Deal After CRM Seed"
        )
        self.assertEqual(generated["deal_id"], "D-113")

    async def test_crm_import_rejects_noncanonical_ids(self):
        csv_content = (
            "deal_id,account_name,deal_value,stage,status\n"
            "legacy-3,Invalid ID Account,50000,Proposal,open\n"
        )

        response = await self.client.post(
            "/api/deals/upload",
            files={"file": ("invalid-id.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("canonical format D-<positive integer>", response.text)
        self.assertEqual((await self.client.get("/api/deals")).json(), [])

    async def test_crm_import_rejects_existing_ids_without_overwriting(self):
        csv_content = (
            "deal_id,account_name,deal_value,stage,status\n"
            "D-900,Original Account,50000,Proposal,open\n"
        )
        upload = {
            "file": ("sample.csv", csv_content, "text/csv")
        }

        first = await self.client.post("/api/deals/upload", files=upload)
        self.assertEqual(first.status_code, 200)

        duplicate_csv = (
            "deal_id,account_name,deal_value,stage,status\n"
            "D-900,Changed Account,999999,Negotiation,open\n"
        )
        second = await self.client.post(
            "/api/deals/upload",
            files={"file": ("duplicate.csv", duplicate_csv, "text/csv")},
        )

        self.assertEqual(second.status_code, 409)
        self.assertIn("no records were changed", second.text)
        deals = await self.client.get("/api/deals")
        self.assertEqual(deals.status_code, 200)
        self.assertEqual(len(deals.json()), 1)
        self.assertEqual(deals.json()[0]["account_name"], "Original Account")
        self.assertEqual(deals.json()[0]["deal_value"], 50000)

    async def test_crm_import_invalid_row_inserts_no_partial_records(self):
        csv_content = (
            "deal_id,account_name,deal_value,stage,status\n"
            "D-910,Valid Account,50000,Proposal,open\n"
            "D-911,Invalid Account,not-a-number,Proposal,open\n"
        )

        response = await self.client.post(
            "/api/deals/upload",
            files={"file": ("invalid.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("row 3", response.text)
        deals = await self.client.get("/api/deals")
        self.assertEqual(deals.status_code, 200)
        self.assertEqual(deals.json(), [])

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
        api_deals = await self.client.get("/api/deals")
        self.assertEqual(
            {deal["deal_id"] for deal in api_deals.json()},
            {"D-101", "D-102", "D-103"},
        )

    async def test_dashboard_csv_import_and_metrics_preserve_crm_fields(self):
        csv_content = (
            "deal_id,account_name,deal_value,stage,status,created_date,"
            "expected_close_date,last_activity_date,activity_count,"
            "meeting_count,email_count,stakeholder_count\n"
            "D-900,Sample Account,50000,Proposal,open,2026-10-01,"
            "2026-11-15,2026-10-27,5,2,3,4\n"
        )

        uploaded = await self.client.post(
            "/api/deals/upload",
            files={"file": ("sample.csv", csv_content, "text/csv")},
        )

        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()["records_imported"], 1)

        deals = await self.client.get("/api/deals")
        self.assertEqual(deals.status_code, 200)
        self.assertEqual(deals.json()[0]["deal_id"], "D-900")
        self.assertEqual(deals.json()[0]["account_name"], "Sample Account")
        self.assertEqual(deals.json()[0]["expected_close_date"], "2026-11-15")

        metrics = await self.client.get("/api/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.json()["total_open_pipeline_value"], 50000)
        crm_top_deal = metrics.json()["top_deals"][0]
        self.assertEqual(crm_top_deal["risk_score"], deals.json()[0]["risk_score"])
        self.assertEqual(
            crm_top_deal["risk_reasons"],
            deals.json()[0]["risk_reasons"],
        )
        self.assertEqual(
            crm_top_deal["recommended_action"],
            deals.json()[0]["recommended_action"],
        )

        analyzed = await self.client.post("/api/deals/D-900/analyze")
        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(analyzed.json()["deal_id"], "D-900")

    async def test_high_risk_endpoint_includes_legacy_probability_risk(self):
        high_risk_deal = await self.create_deal(
            company="Zenith Technologies",
            probability=25,
        )
        await self.create_deal(
            company="Healthy Pipeline",
            probability=75,
        )
        legacy_list = await self.client.get("/deals")
        self.assertEqual(legacy_list.status_code, 200)
        zenith = next(
            deal for deal in legacy_list.json()
            if deal["id"] == high_risk_deal["id"]
        )
        self.assertEqual(zenith["risk_level"], "HIGH")

        response = await self.client.get("/api/deals/high-risk")

        self.assertEqual(response.status_code, 200)
        crm_deals = await self.client.get("/api/deals")
        self.assertEqual(crm_deals.status_code, 200)
        high_deal_id = next(
            deal["deal_id"]
            for deal in crm_deals.json()
            if deal["id"] == high_risk_deal["id"]
        )
        self.assertEqual(
            [deal["deal_id"] for deal in response.json()],
            [high_deal_id],
        )
        self.assertEqual(response.json()[0]["risk_level"], "HIGH")
        self.assertIn(
            "Closing probability is 25%, raising risk to HIGH.",
            response.json()[0]["risk_reasons"],
        )

    async def test_high_risk_endpoint_keeps_open_status_and_crm_risk_rules(self):
        async with self.session_factory() as session:
            session.add_all(
                [
                    Deal(
                        deal_id="D-906",
                        company="High CRM Risk",
                        deal_value=90000,
                        stage="Proposal",
                        probability=25,
                        status="open",
                        risk_score=80,
                        risk_level="HIGH",
                        risk_reasons='["CRM risk"]',
                        recommended_action="Stored CRM recommendation",
                    ),
                    Deal(
                        deal_id="D-907",
                        company="Closed High CRM Risk",
                        deal_value=80000,
                        stage="Proposal",
                        probability=70,
                        status="closed_lost",
                        risk_score=100,
                        risk_level="HIGH",
                        risk_reasons='["CRM risk"]',
                    ),
                    Deal(
                        deal_id="D-908",
                        company="Low CRM Risk",
                        deal_value=70000,
                        stage="Proposal",
                        probability=70,
                        status="open",
                        risk_score=10,
                        risk_level="LOW",
                        risk_reasons="[]",
                    ),
                ]
            )
            await session.commit()

        response = await self.client.get("/api/deals/high-risk")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [deal["deal_id"] for deal in response.json()],
            ["D-906"],
        )
        self.assertEqual(response.json()[0]["risk_level"], "HIGH")
        self.assertEqual(response.json()[0]["risk_score"], 80)
        self.assertEqual(response.json()[0]["risk_reasons"], ["CRM risk"])
        self.assertEqual(
            response.json()[0]["recommended_action"],
            "Stored CRM recommendation",
        )

        all_deals = await self.client.get("/api/deals")
        metrics = await self.client.get("/api/metrics")
        self.assertEqual(all_deals.status_code, 200)
        self.assertEqual(metrics.status_code, 200)
        listed_deal = next(
            deal for deal in all_deals.json()
            if deal["deal_id"] == "D-906"
        )
        metrics_deal = next(
            deal for deal in metrics.json()["top_deals"]
            if deal["deal_id"] == "D-906"
        )
        for deal_response in (listed_deal, metrics_deal):
            self.assertEqual(deal_response["risk_reasons"], ["CRM risk"])
            self.assertEqual(
                deal_response["recommended_action"],
                "Stored CRM recommendation",
            )

    async def test_high_risk_endpoint_returns_empty_list_when_no_deals_qualify(self):
        response = await self.client.get("/api/deals/high-risk")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    async def test_metrics_use_legacy_probability_risk_without_changing_pipeline(self):
        sample_file = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "sample_deals.csv"
        )
        imported = await self.client.post(
            "/deals/import-csv",
            files={
                "file": (
                    sample_file.name,
                    sample_file.read_bytes(),
                    "text/csv",
                )
            },
        )
        self.assertEqual(imported.status_code, 200)
        await self.create_deal(
            company="Fourth Pipeline Deal",
            deal_value=150000,
            stage="Negotiation",
            probability=80,
        )

        with patch(
            "backend.app.main.is_deal_overdue",
            side_effect=lambda expected_close_date, *_: (
                expected_close_date == date(2026, 10, 20)
            ),
        ):
            metrics = await self.client.get("/api/metrics")

        self.assertEqual(metrics.status_code, 200)
        result = metrics.json()
        self.assertEqual(result["high_risk_deals"], 1)
        self.assertEqual(result["revenue_high_risk"], 65000)
        self.assertEqual(result["deals_needing_attention"], 2)
        self.assertEqual(
            result["deal_distribution_by_risk"],
            {"LOW": 2, "MEDIUM": 1, "HIGH": 1},
        )
        self.assertEqual(result["total_open_pipeline_value"], 350000)
        self.assertEqual(
            result["pipeline_value_by_stage"],
            {"Negotiation": 215000, "Proposal": 95000, "Qualified": 40000},
        )
        top_deals = {
            deal["account_name"]: deal
            for deal in result["top_deals"]
        }
        self.assertEqual(set(top_deals), {
            "Zenith Technologies",
            "BlueWave Solutions",
            "PixelCore Systems",
            "Fourth Pipeline Deal",
        })
        self.assertEqual(top_deals["Zenith Technologies"]["risk_level"], "HIGH")
        self.assertIn(
            "Closing probability is 25%, raising risk to HIGH.",
            top_deals["Zenith Technologies"]["risk_reasons"],
        )
        self.assertTrue(
            any(
                "customer activity" in reason.lower()
                for reason in top_deals["Zenith Technologies"]["risk_reasons"]
            )
        )
        self.assertIn(
            "customer follow-up",
            top_deals["Zenith Technologies"]["recommended_action"].lower(),
        )
        self.assertEqual(top_deals["PixelCore Systems"]["risk_level"], "MEDIUM")
        self.assertTrue(
            any(
                "overdue" in reason.lower()
                for reason in top_deals["PixelCore Systems"]["risk_reasons"]
            )
        )
        self.assertTrue(
            top_deals["PixelCore Systems"]["recommended_action"]
        )
        self.assertEqual(top_deals["PixelCore Systems"]["created_date"], None)
        for deal in top_deals.values():
            self.assertGreaterEqual(deal["risk_score"], 0)
            self.assertTrue(deal["risk_reasons"])
            self.assertTrue(deal["recommended_action"])
            self.assertIsNone(deal["created_date"])

        api_deals = await self.client.get("/api/deals")
        high_risk_deals = await self.client.get("/api/deals/high-risk")
        self.assertEqual(api_deals.status_code, 200)
        self.assertEqual(high_risk_deals.status_code, 200)
        api_zenith = next(
            deal for deal in api_deals.json()
            if deal["account_name"] == "Zenith Technologies"
        )
        high_risk_zenith = next(
            deal for deal in high_risk_deals.json()
            if deal["account_name"] == "Zenith Technologies"
        )
        expected_zenith_reasons = top_deals["Zenith Technologies"]["risk_reasons"]
        for deal_response in (api_zenith, high_risk_zenith):
            self.assertEqual(
                deal_response["risk_reasons"],
                expected_zenith_reasons,
            )
            self.assertEqual(
                deal_response["risk_reasons"],
                top_deals["Zenith Technologies"]["risk_reasons"],
            )
            self.assertEqual(
                deal_response["recommended_action"],
                top_deals["Zenith Technologies"]["recommended_action"],
            )
        self.assertEqual(
            api_zenith["recommended_action"],
            top_deals["Zenith Technologies"]["recommended_action"],
        )
        self.assertEqual(
            high_risk_zenith["recommended_action"],
            top_deals["Zenith Technologies"]["recommended_action"],
        )

        async with self.session_factory() as session:
            for company in (
                "Zenith Technologies",
                "BlueWave Solutions",
                "PixelCore Systems",
            ):
                stored_deal = await session.get(
                    Deal,
                    next(
                        deal["id"]
                        for deal in api_deals.json()
                        if deal["account_name"] == company
                    ),
                )
                self.assertIsNotNone(stored_deal)
                self.assertEqual(stored_deal.risk_score, 0)
                self.assertEqual(stored_deal.risk_level, "LOW")
                self.assertEqual(stored_deal.risk_reasons, "[]")
                self.assertEqual(stored_deal.recommended_action, "")
                self.assertTrue(stored_deal.probability_is_known)

        risk_by_company = {
            deal["account_name"]: deal["risk_level"]
            for deal in api_deals.json()
        }
        self.assertEqual(risk_by_company["Zenith Technologies"], "HIGH")
        self.assertEqual(risk_by_company["BlueWave Solutions"], "LOW")
        self.assertEqual(risk_by_company["PixelCore Systems"], "MEDIUM")
        filtered_high_risk = await self.client.get(
            "/api/deals",
            params={"risk_level": "HIGH"},
        )
        self.assertEqual(filtered_high_risk.status_code, 200)
        self.assertEqual(
            [deal["account_name"] for deal in filtered_high_risk.json()],
            ["Zenith Technologies"],
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

    async def test_import_csv_rejects_noncanonical_explicit_id(self):
        csv_content = (
            "deal_id,company,deal_value,stage,probability,expected_close_date\n"
            "legacy-2,Invalid ID,10000,Qualified,50,2026-11-10\n"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("deals.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("canonical format D-<positive integer>", response.text)
        self.assertEqual((await self.client.get("/deals")).json(), [])

    async def test_import_csv_rejects_duplicate_explicit_ids_in_same_file(self):
        csv_content = (
            "deal_id,company,deal_value,stage,probability,expected_close_date\n"
            "D-120,First Account,10000,Qualified,50,2026-11-10\n"
            "D-120,Second Account,20000,Proposal,50,2026-11-20\n"
        )

        response = await self.client.post(
            "/deals/import-csv",
            files={"file": ("duplicates.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Duplicate deal_id 'D-120'", response.text)
        self.assertEqual((await self.client.get("/deals")).json(), [])

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

    async def test_legacy_unknown_probability_uses_overall_risk_level(self):
        created_response = await self.client.post(
            "/deals",
            json={
                "company": "Unknown Probability Legacy Deal",
                "deal_value": 50000,
                "stage": "Proposal",
                "expected_close_date": (
                    date.today() + timedelta(days=60)
                ).isoformat(),
            },
        )
        self.assertEqual(created_response.status_code, 200)
        created = created_response.json()

        list_response = await self.client.get("/deals")
        detail_response = await self.client.get(f"/deals/{created['id']}")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        listed = next(
            deal for deal in list_response.json()
            if deal["id"] == created["id"]
        )
        for deal_response in (
            created,
            listed,
            detail_response.json(),
        ):
            self.assertEqual(deal_response["risk_level"], "MEDIUM")
            self.assertEqual(deal_response["overall_risk_level"], "MEDIUM")
            self.assertEqual(deal_response["probability"], 50)
            self.assertFalse(deal_response["probability_is_known"])

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
                with patch("backend.app.main.SessionLocal") as session_local:
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
                with patch("backend.app.main.SessionLocal") as session_local:
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
        with patch("backend.app.main.SessionLocal") as session_local:
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
                with patch("backend.app.main.SessionLocal") as session_local:
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
                with patch("backend.app.main.SessionLocal") as session_local:
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

        with patch("backend.app.main.SessionLocal", FailingSession):
            with self.assertLogs("uvicorn.error", level="ERROR") as captured:
                response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"detail": "Database operation failed"},
        )
        log_output = "\n".join(captured.output)
        self.assertIn("GET /deals", log_output)
        self.assertIn("simulated database failure", log_output)
        self.assertIn("Traceback", log_output)

    async def test_missing_model_column_is_logged_without_leaking_to_response(self):
        class MissingColumnSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def execute(self, statement):
                class UndefinedColumnError(Exception):
                    sqlstate = "42703"

                raise ProgrammingError(
                    str(statement),
                    {},
                    UndefinedColumnError("column deals.deal_id does not exist"),
                )

        with patch("backend.app.main.SessionLocal", MissingColumnSession):
            with self.assertLogs("uvicorn.error", level="ERROR") as captured:
                response = await self.client.get("/deals")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Database schema is incompatible with this application; "
                    "administrator action is required"
                )
            },
        )
        self.assertNotIn("deals.deal_id", response.text)
        self.assertIn("GET /deals", "\n".join(captured.output))
        self.assertIn("deals.deal_id", "\n".join(captured.output))

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

        with patch("backend.app.main.SessionLocal", FailingSession):
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

        with patch("backend.app.main.SessionLocal", FailingSession):
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
