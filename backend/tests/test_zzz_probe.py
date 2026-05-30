from datetime import datetime, timedelta, timezone
from app.constants import LeadStatus, SourceChannel
from app.models.lead import Lead
from app.services import summary_inputs as si

_SUN = datetime(2026, 5, 31, 5, 0, tzinfo=timezone.utc)


async def test_probe(db):
    ws = _SUN - timedelta(days=7)
    we = _SUN
    created = ws + timedelta(days=1)
    l1 = Lead(full_name="x", source_channel=SourceChannel.MANUAL.value,
              status=LeadStatus.IN_PROGRESS.value, created_at=created,
              first_outbound_at=created + timedelta(hours=2))
    db.add(l1)
    await db.flush()
    from sqlalchemy import select, func
    rows = (await db.execute(select(Lead.id, Lead.created_at, Lead.first_outbound_at))).all()
    info = []
    for r in rows:
        info.append(f"created={r[1]} fo={r[2]}")
    open("/tmp/probe_rows.txt","w").write("ROWS:%d\n%s\n" % (len(rows), "\n".join(info)))
    avg = await si._avg_first_response_hours(db, ws, we)
    open("/tmp/probe_avg.txt","w").write("AVG=%r WS=%s WE=%s\n" % (avg, ws, we))
    assert True
