

# First-Order 📈

Una plataforma global de investigación y lista de seguimiento del mercado de valores construida con FastAPI y PostgreSQL.

Rastrea acciones en 14 mercados, lee noticias en tiempo real y escribe notas de investigación con marca de tiempo e instantáneas de precio, todo a través de una API REST limpia.

**En vivo:** https://first-order-a3v1.onrender.com/docs

---

## Qué hace

- **Lista de seguimiento (Watchlist)** — agrega cualquier acción por su símbolo; se crea automáticamente si no está en la base de datos
- **Precios en vivo** — obtiene datos en tiempo real para cualquier símbolo compatible con Yahoo Finance
- **Noticias del mercado** — titulares recientes por acción, con respaldo RSS si la fuente principal limita las solicitudes
- **Vista global** — 14 índices principales obtenidos en paralelo
- **Notas de investigación** — notas privadas por acción con el precio capturado automáticamente al crearlas
- **Autenticación** — JWT + hash de contraseñas con Argon2, flujo completo de registro e inicio de sesión

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Framework | FastAPI |
| Base de datos | PostgreSQL (async via asyncpg) |
| ORM | SQLAlchemy 2.0 (estilo Mapped / mapped_column) |
| Migraciones | Alembic |
| Autenticación | PyJWT + pwdlib (Argon2) |
| Datos del mercado | yfinance + feedparser (respaldo RSS) |
| Configuración | pydantic-settings |
| Contenedor | Docker + docker-compose |
| Despliegue | Render + UptimeRobot |

---

## Formato de Símbolos por Mercado

Yahoo Finance utiliza sufijos de bolsa. Aquí tienes qué usar por mercado:

| Mercado | Sufijo | Ejemplo |
|---|---|---|
| India (NSE) | `.NS` | `RELIANCE.NS`, `TCS.NS`, `HAL.NS` |
| India (BSE) | `.BO` | `RELIANCE.BO` |
| EE. UU. | *(ninguno)* | `AAPL`, `NVDA`, `META` |
| Alemania (XETRA) | `.DE` | `VOW3.DE`, `SAP.DE` |
| Japón (TSE) | `.T` | `7203.T` (Toyota), `6758.T` (Sony) |
| Reino Unido (LSE) | `.L` | `SHEL.L`, `HSBA.L` |
| Hong Kong | `.HK` | `0700.HK` (Tencent), `9988.HK` (Alibaba) |
| China (Shanghái) | `.SS` | `600519.SS` (Moutai) |
| China (Shenzhen) | `.SZ` | `000001.SZ` |
| Taiwán | `.TW` | `2330.TW` (TSMC) |
| Corea del Sur | `.KS` | `005930.KS` (Samsung) |
| Francia (Euronext) | `.PA` | `MC.PA` (LVMH), `AI.PA` |
| Países Bajos | `.AS` | `ASML.AS` |
| Canadá (TSX) | `.TO` | `RY.TO`, `SU.TO` |

> **Nota:** Las acciones de PYMES, microcapitalización y empresas recientemente listadas pueden tener datos incompletos en Yahoo Finance. Las de gran capitalización funcionan de manera confiable.

---

## Endpoints de la API

### Autenticación
```
POST /auth/register    — crear cuenta
POST /auth/login       — devuelve el token JWT
GET  /auth/me          — perfil del usuario actual (protegido)
```

### Lista de seguimiento (protegida)
```
GET    /watchlist/            — obtener tu lista de seguimiento completa
POST   /watchlist/{symbol}    — agregar una acción (ej. /watchlist/RELIANCE.NS)
DELETE /watchlist/{symbol}    — eliminar una acción
```

### Mercado (público)
```
GET /market/price/{symbol}       — precio en vivo, cambio %, volumen, rango de 52 semanas
GET /market/news/{symbol}        — titulares recientes de una acción
GET /market/overview             — instantánea de 14 índices globales
GET /market/stocks/search?q=...  — buscar acciones en la base de datos por nombre o símbolo
```

### Notas de investigación (protegidas)
```
POST   /notes/{symbol}           — crear nota (el precio se captura automáticamente)
GET    /notes/                   — todas tus notas en todas las acciones
GET    /notes/stock/{symbol}     — todas las notas de una acción específica
PATCH  /notes/{note_id}          — actualizar una nota
DELETE /notes/{note_id}          — eliminar una nota
```

### Estado del servicio (Health)
```
GET /health    — estado del servicio
```

---

## Cómo probarlo en vivo

**1. Abre la documentación:**
https://first-order-a3v1.onrender.com/docs

**2. Registra una cuenta:**
- Ve a `POST /auth/register`
- Haz clic en *Try it out*
- Completa el correo electrónico, nombre de usuario y contraseña
- Ejecuta

**3. Inicia sesión y obtén tu token:**
- Ve a `POST /auth/login`
- Haz clic en *Try it out*
- Completa el correo electrónico y la contraseña
- Ejecuta
- Copia el `access_token` de la respuesta

**4. Autoriza:**
- Haz clic en el botón **Authorize** en la parte superior de la página
- En el campo **username**, ingresa tu **correo electrónico** (el formulario OAuth2 lo mapea así)
- Ingresa tu contraseña
- Haz clic en Authorize

Ahora has iniciado sesión. Todos los endpoints protegidos (watchlist, notes, /me) funcionarán.

**5. Prueba algunos endpoints:**
```
GET /market/price/RELIANCE.NS      — Reliance Industries live price
GET /market/price/AAPL             — Apple live price
GET /market/news/TCS.NS            — TCS latest news
GET /market/overview               — all 14 global indices
POST /watchlist/HAL.NS             — add HAL to your watchlist
POST /notes/CDSL.NS                — write a research note on CDSL
```

> **Nota:** El plan gratuito de Render se detiene tras períodos de inactividad. La primera solicitud puede tardar ~30 segundos si el servicio está en frío. Las solicitudes posteriores serán rápidas.

---

## Ejecutar localmente con Docker

```bash
git clone https://github.com/ah4ddd/first-order
cd first-order

# Copia y completa tus variables de entorno
cp .env.example .env

# Inicia todo
docker compose up --build

# En una segunda terminal: ejecuta las migraciones y los datos iniciales
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed_stocks
```

Abre http://localhost:8000/docs

### Variables de Entorno

```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@db/first_order
SECRET_KEY=your-32-byte-hex-key   # genera con: openssl rand -hex 32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
APP_NAME=First-Order
DEBUG=True
NEWS_API_KEY=                      # opcional
```

---

## Estructura del Proyecto

```
first-order/
├── app/
│   ├── main.py              — aplicación FastAPI, middleware, registro de routers
│   ├── config.py            — configuración pydantic-settings
│   ├── database.py          — motor async, fábrica de sesiones, dependencia get_db
│   ├── db_models.py         — modelos de tablas SQLAlchemy 2.0 (estilo Mapped)
│   ├── models.py            — esquemas de solicitud/respuesta de Pydantic
│   ├── dependencies.py      — dependencia de autenticación JWT, alias de tipo CurrentUser
│   ├── utils.py             — get_or_create_stock, inferencia de país
│   ├── seed_stocks.py       — sembrador de datos iniciales de acciones
│   ├── services/
│   │   └── rss_news.py      — obtentor de feeds RSS (respaldo de noticias)
│   └── routers/
│       ├── auth.py          — registro, inicio de sesión, /me
│       ├── watchlist.py     — CRUD de lista de seguimiento
│       ├── market.py        — precios, noticias, vista general, búsqueda
│       └── notes.py         — CRUD de notas de investigación
├── alembic/                 — migraciones de base de datos
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Notas de Arquitectura

**Async en todo el flujo** — utiliza `AsyncSession` de SQLAlchemy 2.0 y el controlador `asyncpg`. Cada llamada a la base de datos es no bloqueante.

**yfinance en threadpool** — yfinance es síncrono. Todas las llamadas están envueltas con `asyncio.to_thread` para que el event loop permanezca libre ante solicitudes concurrentes.

**Obtención paralela de índices** — el endpoint de vista global del mercado lanza 14 solicitudes de yfinance simultáneamente usando `asyncio.gather`. El tiempo de respuesta se mantiene estable sin importar cuántos índices se agreguen.

**Caché en memoria** — los precios se almacenan en caché por 60 segundos, las noticias por 5 minutos y la vista global por 2 minutos. Evita saturar las APIs externas con solicitudes repetidas.

**Obtener-o-crear acciones** — cuando un usuario agrega un símbolo a su lista de seguimiento o crea una nota, si la acción aún no está en la base de datos, se crea automáticamente obteniendo metadatos de yfinance. No es necesario sembrar manualmente nuevos símbolos.

**Instantánea de precio en notas** — cuando se crea una nota de investigación, el precio de mercado actual se captura y almacena permanentemente. Te permite ver a qué precio estabas mirando cuando escribiste el análisis.

**Respaldo RSS para noticias** — si las noticias de yfinance están limitadas por rate-limit (común en IPs de proveedores de nube), el endpoint de noticias recurre a feeds RSS de Reuters, BBC Business, Economic Times y Moneycontrol.

---

## Limitaciones Conocidas

- **Rate limiting de yfinance** — Yahoo Finance bloquea ocasionalmente solicitudes desde IPs de proveedores de nube. Los endpoints de precio pueden devolver 503 y reintentar tras una breve espera. Las noticias tienen respaldo RSS.
- **Arranques en frío del plan gratuito** — el plan gratuito de Render se detiene tras 15 minutos de inactividad. UptimeRobot envía pings cada 5 minutos para mitigar esto.
- **Sin streaming en tiempo real** — los precios se obtienen bajo demanda, no se empujan (push). Refresca el endpoint para obtener datos actualizados.
- **Acciones de PYMES en India** — las de pequeño/micro capital y empresas recientemente listadas pueden tener metadatos incompletos en Yahoo Finance.

---

## Próximos Pasos

- [ ] Frontend mínimo (panel de control, página de detalle de acción, vista de lista de seguimiento)
- [ ] Posiciones de cartera con seguimiento de ganancias y pérdidas (P&L)
- [ ] Feed de noticias geopolíticas/macroeconómicas
- [ ] Resumen de notas impulsado por IA

---

## Acerca de

Desarrollado por Ahad ([@ah4ddd](https://github.com/ah4ddd))

Este es mi primer proyecto real de portafolio con FastAPI.
