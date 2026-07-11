import httpx
import pytest

from th_verify.collectors.cofact import CofactCollector, clean_html


def test_clean_html():
    assert clean_html("<p>สวัสดี <strong>โลก</strong></p>") == "สวัสดี โลก"


@pytest.mark.asyncio
async def test_cofact_delta():
    sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url>
      <loc>https://blog.cofact.org/th/example/</loc><lastmod>2024-01-01T00:00:00Z</lastmod>
    </url></urlset>"""
    article = """<html><head><meta property="article:published_time" content="2024-01-01T00:00:00Z"></head>
      <main id="site-content"><article id="post-7" class="post-7 post"><h1>คำกล่าวอ้าง</h1>
      <div class="entry-content">คำอธิบาย เนื้อหาเป็นเท็จ</div></article></main></html>"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=sitemap if "sitemap" in str(request.url) else article)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        records = [r async for r in CofactCollector(client).collect(mode="delta")]
    assert records[0].source_id == "7"
    assert records[0].title == "คำกล่าวอ้าง"
