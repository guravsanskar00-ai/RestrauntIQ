from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3, json, os, re
from datetime import datetime

DB = "restaurantiq.db"
app = FastAPI(title="RestaurantIQ")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Compatibility wrapper: supports both older and newer Starlette TemplateResponse APIs.
_original_template_response = templates.TemplateResponse

def _compatible_template_response(*args, **kwargs):
    if args and isinstance(args[0], str):
        template_name = args[0]
        context = args[1] if len(args) > 1 else kwargs.pop("context", {})
        return _original_template_response(
            request=context.get("request"),
            name=template_name,
            context=context,
            **kwargs,
        )
    return _original_template_response(*args, **kwargs)

templates.TemplateResponse = _compatible_template_response

SEED = [
    ("The Food Corner","Pune","North Indian",4.5,1256,600,65,78),
    ("Spice Hub","Pune","Chinese",3.8,842,450,48,52),
    ("Meal Magic","Pune","Fast Food",2.9,512,350,32,28),
    ("Urban Bites","Mumbai","Cafe",3.2,340,500,41,35),
    ("Tasty Treat","Nashik","South Indian",4.1,690,300,59,71),
]

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c=conn()
    c.execute("""CREATE TABLE IF NOT EXISTS restaurants(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, city TEXT, cuisine TEXT,
        rating REAL, reviews INTEGER, price INTEGER, sentiment INTEGER, survival INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT, restaurant_id INTEGER, reviewer TEXT,
        review TEXT, sentiment TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)""")
    if c.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0] == 0:
        c.executemany("INSERT INTO restaurants(name,city,cuisine,rating,reviews,price,sentiment,survival) VALUES(?,?,?,?,?,?,?,?)", SEED)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.execute("INSERT INTO users(username,password) VALUES(?,?)", ("admin","admin123"))
    c.commit(); c.close()

init_db()

def all_restaurants():
    c=conn(); rows=c.execute("SELECT * FROM restaurants ORDER BY id DESC").fetchall(); c.close()
    return [dict(r) for r in rows]

def get_restaurant(rid):
    c=conn(); r=c.execute("SELECT * FROM restaurants WHERE id=?",(rid,)).fetchone(); c.close()
    return dict(r) if r else None

def sentiment_for(text):
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        score=SentimentIntensityAnalyzer().polarity_scores(text)["compound"]
    except Exception:
        positive=["great","good","excellent","love","amazing","friendly","delicious","fast","best","fresh"]
        negative=["bad","poor","terrible","hate","slow","dirty","expensive","worst","rude","cold"]
        t=text.lower()
        score=sum(w in t for w in positive)*0.35 - sum(w in t for w in negative)*0.4
    return "Positive" if score >= 0.05 else ("Negative" if score <= -0.05 else "Neutral")

def popularity(r):
    # Transparent demo score. Replace with a trained model for research evaluation.
    score = (r["rating"] / 5 * 40) + (min(r["reviews"],2000)/2000*20) + (r["sentiment"]/100*25) + (r["survival"]/100*15)
    return max(0,min(100,round(score)))

def risk(r):
    p=round((r["rating"]/5*35)+(r["sentiment"]/100*30)+(r["survival"]/100*35))
    return ("Low",p) if p>=70 else (("Medium",p) if p>=45 else ("High",p))

def recommendations(r):
    out=[]
    if r["rating"] < 4: out.append(("Improve service quality","Review customer complaints and train staff to improve ratings.","High"))
    if r["sentiment"] < 60: out.append(("Respond to customer feedback","Reply to negative reviews and resolve repeated issues.","High"))
    if r["reviews"] < 700: out.append(("Increase online visibility","Ask satisfied customers for honest reviews and update business listings.","Medium"))
    if r["price"] > 500: out.append(("Review pricing","Compare popular nearby restaurants and test value meal bundles.","Medium"))
    if not out: out=[("Maintain quality","Keep service consistent and refresh the menu based on customer feedback.","High"),
                      ("Promote signature dishes","Feature your best-rated dishes in online posts and offers.","Medium")]
    return out

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request":request, "error":""})

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str=Form(...), password: str=Form(...)):
    c=conn(); user=c.execute("SELECT * FROM users WHERE username=? AND password=?",(username,password)).fetchone(); c.close()
    if user: return RedirectResponse("/dashboard",status_code=303)
    return templates.TemplateResponse("login.html",{"request":request,"error":"Invalid login. Demo: admin / admin123"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    rs=all_restaurants()
    return templates.TemplateResponse("dashboard.html",{"request":request,"restaurants":rs,"total":len(rs),
        "avg":round(sum(r["rating"] for r in rs)/max(1,len(rs)),1),
        "avgpop":round(sum(popularity(r) for r in rs)/max(1,len(rs)),1),
        "highrisk":sum(risk(r)[0]=="High" for r in rs)})

@app.get("/reviews", response_class=HTMLResponse)
def reviews_page(request: Request):
    c=conn()
    rows=c.execute("""SELECT reviews.*, restaurants.name AS restaurant_name FROM reviews
       LEFT JOIN restaurants ON restaurants.id=reviews.restaurant_id ORDER BY reviews.id DESC""").fetchall()
    rs=c.execute("SELECT id,name FROM restaurants").fetchall()
    c.close()
    counts={"Positive":0,"Neutral":0,"Negative":0}
    for row in rows:
        if row["sentiment"] in counts: counts[row["sentiment"]]+=1
    return templates.TemplateResponse("reviews.html",{"request":request,"reviews":[dict(x) for x in rows],
        "restaurants":[dict(x) for x in rs],"counts":counts})

@app.post("/reviews")
def add_review(restaurant_id: int=Form(...), reviewer: str=Form("Guest"), review: str=Form(...)):
    label=sentiment_for(review)
    c=conn()
    c.execute("INSERT INTO reviews(restaurant_id,reviewer,review,sentiment,created_at) VALUES(?,?,?,?,?)",
        (restaurant_id,reviewer.strip() or "Guest",review,label,datetime.now().strftime("%d %b %Y %H:%M")))
    # Update sentiment aggregate using recent review labels.
    r=c.execute("SELECT * FROM restaurants WHERE id=?",(restaurant_id,)).fetchone()
    rows=c.execute("SELECT sentiment FROM reviews WHERE restaurant_id=?",(restaurant_id,)).fetchall()
    if rows:
        positive=sum(x["sentiment"]=="Positive" for x in rows)
        sentiment=round(positive/len(rows)*100)
        c.execute("UPDATE restaurants SET sentiment=? WHERE id=?",(sentiment,restaurant_id))
    c.commit(); c.close()
    return RedirectResponse("/reviews",status_code=303)

@app.get("/popularity", response_class=HTMLResponse)
def popularity_page(request: Request):
    rs=all_restaurants()
    return templates.TemplateResponse("popularity.html",{"request":request,"restaurants":rs,
        "results":[{"r":r,"score":popularity(r)} for r in rs]})

@app.post("/popularity", response_class=HTMLResponse)
def popularity_predict(request: Request, name: str=Form(...), city: str=Form("Pune"),
        cuisine: str=Form("Other"), rating: float=Form(...), reviews: int=Form(...),
        price: int=Form(...), sentiment: int=Form(...), survival: int=Form(...)):
    r={"name":name,"city":city,"cuisine":cuisine,"rating":max(0,min(5,rating)),
       "reviews":max(0,reviews),"price":max(0,price),"sentiment":max(0,min(100,sentiment)),
       "survival":max(0,min(100,survival))}
    rs=all_restaurants()
    return templates.TemplateResponse("popularity.html",{"request":request,"restaurants":rs,
        "prediction":{"name":name,"score":popularity(r)}})

@app.get("/survival", response_class=HTMLResponse)
def survival_page(request: Request):
    rs=all_restaurants()
    results=[{"r":r,"risk":risk(r)[0],"prob":risk(r)[1]} for r in rs]
    return templates.TemplateResponse("survival.html",{"request":request,"results":results})

@app.get("/recommendations", response_class=HTMLResponse)
def recommendations_page(request: Request, rid: int=1):
    rs=all_restaurants()
    selected=get_restaurant(rid) or (rs[0] if rs else None)
    return templates.TemplateResponse("recommendations.html",{"request":request,"restaurants":rs,
        "selected":selected,"recommendations":recommendations(selected) if selected else []})

@app.get("/comparison", response_class=HTMLResponse)
def comparison_page(request: Request):
    return templates.TemplateResponse("comparison.html",{"request":request,"restaurants":all_restaurants()})

@app.get("/restaurants", response_class=HTMLResponse)
def restaurants_page(request: Request):
    return templates.TemplateResponse("restaurants.html",{"request":request,"restaurants":all_restaurants()})

@app.post("/restaurants")
def add_restaurant(name: str=Form(...), city: str=Form(...), cuisine: str=Form(...),
    rating: float=Form(...), reviews: int=Form(...), price: int=Form(...)):
    rating=max(0,min(5,rating)); reviews=max(0,reviews); price=max(0,price)
    sentiment=70 if rating>=4 else (50 if rating>=3 else 30)
    survival=round(rating/5*55+sentiment/100*45)
    c=conn()
    try:
        c.execute("INSERT INTO restaurants(name,city,cuisine,rating,reviews,price,sentiment,survival) VALUES(?,?,?,?,?,?,?,?)",
            (name,city,cuisine,rating,reviews,price,sentiment,survival))
        c.commit()
    except sqlite3.IntegrityError:
        pass
    c.close()
    return RedirectResponse("/restaurants",status_code=303)

@app.get("/api/restaurants")
def api_restaurants():
    return [{"id":r["id"],"name":r["name"],"popularity":popularity(r),"risk":risk(r)[0],"survival_probability":risk(r)[1]} for r in all_restaurants()]
