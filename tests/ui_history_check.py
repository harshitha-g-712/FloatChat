"""Headless-browser checks for the history sidebar (not collected by pytest).

Run manually:  pip install playwright && playwright install chromium
  cd backend && AUTH_DB_PATH=/tmp/ui_auth.db python -m uvicorn main:app --port 8765 &
  python tests/ui_history_check.py
"""
import json, uuid, requests
from playwright.sync_api import sync_playwright
BASE="http://localhost:8765"
tag=uuid.uuid4().hex[:8]
requests.post(BASE+"/api/register",json={"username":"ui_"+tag,"email":f"ui_{tag}@example.com","password":"Str0ng-Pass-"+tag})
r=requests.post(BASE+"/api/login",json={"email":f"ui_{tag}@example.com","password":"Str0ng-Pass-"+tag}).json()
tok=r["token"]; H={"Authorization":"Bearer "+tok}
old_id=str(uuid.uuid4())
requests.post(BASE+"/api/chat",json={"message":"Average temperature in March 2023","conversation_id":old_id},headers=H)
results=[]
def check(name,ok,extra=""):
    results.append(ok); print(("PASS " if ok else "FAIL ")+name, extra)

with sync_playwright() as p:
    b=p.chromium.launch()
    def page_with_token(token=tok):
        ctx=b.new_context(); pg=ctx.new_page()
        pg.add_init_script(f"localStorage.setItem('floatchat-token','{token}')")
        return ctx,pg

    # A1: network failure on /api/me keeps token
    ctx,pg=page_with_token()
    pg.route("**/api/me", lambda route: route.abort())
    pg.goto(BASE); pg.wait_for_timeout(800)
    check("A1 network error keeps token", pg.evaluate("localStorage.getItem('floatchat-token')")==tok)
    check("A1 app shell visible with retry msg", pg.locator("#app-shell").is_visible() and "Retrying" in pg.locator(".status-bar").inner_text())
    ctx.close()
    # A2: 500 keeps token
    ctx,pg=page_with_token()
    pg.route("**/api/me", lambda route: route.fulfill(status=500, body="{}"))
    pg.goto(BASE); pg.wait_for_timeout(800)
    check("A2 500 keeps token", pg.evaluate("localStorage.getItem('floatchat-token')")==tok)
    ctx.close()
    # A3: 401 logs out
    ctx,pg=page_with_token()
    pg.route("**/api/me", lambda route: route.fulfill(status=401, body='{"detail":"x"}', content_type="application/json"))
    pg.goto(BASE); pg.wait_for_timeout(800)
    check("A3 401 clears token + shows sign-in", pg.evaluate("localStorage.getItem('floatchat-token')") is None and pg.locator("#auth-screen").is_visible())
    ctx.close()
    # A4: transient failure then recovery
    ctx,pg=page_with_token()
    state={"fail":True}
    def me(route):
        if state["fail"]: route.abort()
        else: route.continue_()
    pg.route("**/api/me", me)
    pg.goto(BASE); pg.wait_for_timeout(600)
    state["fail"]=False
    pg.wait_for_timeout(5600)
    check("A4 auto-recovers after server returns", pg.locator("#app-shell").is_visible() and pg.locator("#conversation-list .conv-item").count()>=1 and "hidden" in pg.locator(".status-bar").get_attribute("class"))
    ctx.close()

    # B: New chat cancels slow in-flight load
    ctx,pg=page_with_token()
    def slow(route):
        pg.wait_for_timeout(1500); route.continue_()
    pg.route("**/api/conversations/*/messages", lambda route: slow(route))
    pg.goto(BASE); pg.wait_for_timeout(2500)
    pg.locator("#conversation-list .conv-item-title").first.click()
    pg.wait_for_timeout(200)
    pg.click("#new-chat-btn")
    pg.wait_for_timeout(2500)
    check("B new chat not overwritten by late load", pg.locator("#messages .message-row").count()==0 and pg.locator("#welcome-card").is_visible())
    ctx.close()

    # C: load more
    ctx,pg=page_with_token()
    reqs=[]
    def convs(route):
        url=route.request.url; reqs.append(url)
        lim=int(url.split("limit=")[1].split("&")[0])
        items=[{"id":f"c{i}","title":f"Chat {i}","message_count":2} for i in range(min(lim,230))]
        route.fulfill(status=200,content_type="application/json",body=json.dumps({"conversations":items}))
    pg.route("**/api/conversations?limit=*", convs)
    pg.goto(BASE); pg.wait_for_timeout(1500)
    check("C1 100 rows + Load more button", pg.locator("#conversation-list .conv-item").count()==100 and pg.locator(".conv-more").count()==1)
    pg.click(".conv-more"); pg.wait_for_timeout(700)
    check("C2 second page requests limit=200", any("limit=200" in u for u in reqs) and pg.locator("#conversation-list .conv-item").count()==200)
    pg.click(".conv-more"); pg.wait_for_timeout(700)
    check("C3 last page (230) hides button", pg.locator("#conversation-list .conv-item").count()==230 and pg.locator(".conv-more").count()==0)
    ctx.close()

    # D: export 409 shows server message
    ctx,pg=page_with_token()
    pg.goto(BASE); pg.wait_for_timeout(1500)
    pg.locator("#conversation-list .conv-item-title").first.click(); pg.wait_for_timeout(1200)
    # server cache is fresh (chat just made), so force the 409 via route to test UI path
    pg.route("**/api/export", lambda route: route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail":"Export data is no longer available for this chat. Ask the question again, then export."})))
    if pg.locator(".export-csv-btn").count():
        pg.locator(".export-csv-btn").first.click(); pg.wait_for_timeout(500)
        check("D export 409 detail shown", "Ask the question again" in pg.locator(".status-bar").inner_text())
    else:
        check("D export button present on reopened chat", False)
    ctx.close()
    b.close()
print("TOTAL", sum(results), "/", len(results))
