# Página unificada "Recomendaciones para X"
Repo: cemedinan/forecastquant-posts (clon local: /workspace/site). Live: https://cemedinan.github.io/forecastquant-posts/

Rerun:
1. `python3 build_site.py` (lee data.json en vivo de Poster; o `python3 build_site.py archivo.json /ruta/repo`).
2. Hits nuevos sin imagen salen como "gráfico pendiente". Para agregar imagen: generar PNG (estilo en /workspace/charts/mk2.py, mk3.py), copiarlo a repo/images/ y añadir `{"<url del post>": {"image": "NN_x.png", "origin": "poster"|"venn"}}` (o `{"pending": "motivo"}`) en image_map.json.
3. `cd /workspace/site && git add -A && git commit -m update && git push`.
Archivos: image_map.json (url -> imagen), own_posts.json (posts propios con id estable t0..t13), poster_processed.json (urls ya procesadas).
4. Botón "Actualizar" (sticky arriba) recarga con ?v=<timestamp> y conserva el filtro vía #f=g|n; metas no-cache en <head>. Commit: usar git -c user.name=cemedinan -c user.email=cemedinan@users.noreply.github.com.
5. Formato de imágenes (desde 2026-10-29): TODO gráfico nuevo se produce VERTICAL 4:5 para X (figsize 8x10 in a dpi 270 = 2160x2700, mínimo 1080x1350) y se nombra `*_v.png`. Ver chart_format_rules.md. Helpers: /workspace/charts/vstyle.py (newfig/header/footer/wmark/save), tarjetas explicativas en /workspace/charts/mkv_explain.py (función cards()), wrapper para scripts 16:9 existentes: /workspace/charts/vharness.py. image_map.json y own_posts.json ya apuntan a los `_v.png`; los 16:9 antiguos siguen en images/ y la tarjeta muestra "Ver versión horizontal" si existe el archivo sin `_v`. La rutina debe generar solo `_v.png` y registrarlos así en image_map.json.
6. Descartar tarjetas (desde 2026-10-29): cada <article class="card"> lleva data-id = clave estable (URL del post de Poster, o id t0..tNN de own_posts.json). Deslizar a la izquierda >90px (pointer events, solo gesto horizontal; no actúa sobre botones/pre) o el botón "✕ Descartar" la oculta; Toast "Deshacer" 6 s; enlace "Descartadas (N)" con Restaurar / Restaurar todas / Copiar lista / Pegar lista. Persistencia en localStorage key `fq_dismissed_v1` (array de data-id); un script en <head> oculta las descartadas antes del primer pintado. El servidor sigue generando TODAS las tarjetas; NO cambiar el formato de las claves o se pierden los descartes. Limitación: localStorage es por navegador/dispositivo (no se sincroniza; usar Copiar/Pegar lista para pasarla). Backup previo: build_site.py.bak_preswipe.


## Fuente de datos de Poster (desde 2026-10-29)
Leer /workspace/poster_data.json (Poster lo sobrescribe en cada actualizacion). Respaldo: https://cemedinan.github.io/x-virality-board/data.json solo si el archivo falta.
7. Temas DÍA / NOCHE 50/50 (desde 2026-10-29, pedido del usuario): las imágenes de la página van ~mitad tema "día" y mitad "noche", intercaladas en el orden de la página (una imagen por tarjeta, nunca ambas). Noche = fondo #0B0D26, Bitcoin blanco, resto lima #C6E427. Día = fondo #F2F3F6, azul marino #0B0D26 en lo que en noche era blanco/gris (Bitcoin en azul marino, barras grises→navy), lima en el elemento principal, textos navy, subtítulos #5B6075, grid #DADDE5 (referencia /workspace/charts/mk_light.py opción A). Logo: 6% del ancho (40% más chico); en día versión clara (lima + flecha inferior navy, transparente). Nombres: `NN_x_dia_v.png` / `NN_x_noche_v.png`; los `NN_x_v.png` noche previos se conservan en images/. image_map.json lleva `theme` ("dia"|"noche") y `noche_original`; own_posts.json lleva `theme`. La rutina: cada gráfico nuevo se genera en ambos temas, y se asigna a la tarjeta el tema que mantenga la alternancia/50-50 (contar los temas actuales en image_map antes de asignar). Conversión de una imagen noche existente a día (o noche con logo 6%), sin tocar datos: `python3 retheme.py in_v.png out_dia_v.png dia|noche` (recolor por píxeles + reemplazo de logo); revisar el resultado: no sirve si el gráfico usa sombreados blancos semitransparentes grandes (p. ej. 02_ath_bet) o si el texto nombra colores ("white"/"grey", p. ej. 56) → dejar esos en noche. PNG cuantizados a 256 colores con PIL. Backups: *.bak_pretheme. La etiqueta de la tarjeta muestra "· tema día/noche".
8. Botones X (desde 2026-10-29, pedido del usuario): build_site.py agrega AUTOMÁTICAMENTE a cada bloque, junto a "Copiar texto": "Abrir en X" (Post nuevo → https://x.com/intent/post?text=<quote(texto,safe='')>), "Citar en X" (Quote → text=<texto>\n<URL del post de referencia>; X lo muestra como cita), "Responder en X" (Reply → text=<ángulo>&in_reply_to=<id de /status/>; marcado como ángulo). Posts propios: solo "Abrir en X". Nota "más de 280 caracteres" si aplica. Los intent de X NO pueden adjuntar imágenes. Nunca se publica nada solo. Toda tarjeta nueva de la rutina obtiene estos botones al reconstruir; no hace falta nada extra. Backup: build_site.py.bak_preintent.

9. IMÁGENES (2026-10-29, pedido del usuario): NO hay botones de imagen ("Copiar imagen", "Post con imagen", "Compartir con imagen" fueron ELIMINADOS; no volver a agregarlos). El usuario copia la imagen tocándola/manteniéndola pulsada en Safari y la pega en X tras "Abrir en X". La imagen debe seguir siendo un <img> normal, sin user-select/-webkit-touch-callout: none. Se mantiene el enlace "Descargar imagen". Backup: build_site.py.bak_preimgbtn.

10. App de X en iPhone/iPad (2026-10-29, backup build_site.py.bak_predeeplink): el href de los botones .xb sigue siendo https://x.com/intent/post?... (base sin JS, escritorio, Android). En iOS (userAgent iPhone/iPad/iPod o iPadOS MacIntel+touch) un listener de click hace preventDefault y abre twitter://post?message=<encodeURIComponent(text)>[&in_reply_to_status_id=<id>] (función xdeep, extrae text/in_reply_to del href; la cita mantiene la URL del post en el texto). Si en 1.5 s la página sigue visible (visibilitychange no ocultó), va al href web. Verificado en jsdom (86/86 textos idénticos). NO probado en iPhone real; Safari puede mostrar "¿Abrir en X?" la primera vez. Revertir: quitar xdeep + el listener del js de build_site.py (o restaurar el backup), rebuild y push. x:// no se usa (esquema no documentado; twitter:// es el que la app sigue registrando).

## Regla: logo (marca de agua) — un único punto de estampado
- Un único punto de estampado de logo; nunca estampar sobre una imagen que ya lo tenga.
- Scripts de gráficos (vstyle.py `wmark`, mk_light.py `logo`): llamar UNA sola vez por figura.
- retheme.py: borra primero el logo de la fuente (rellena con el fondo, conservando texto de ejes) y luego estampa el único logo (6% del ancho) en el mismo centro. No re-procesar salidas de retheme (`*_dia_v.png`/`*_noche_v.png`/`*_r2_*`); usar siempre el `*_v.png` original como fuente.
- 2026-10-29: 35 imágenes de retheme tenían logo doble (el borrado viejo fallaba con el logo semitransparente); regeneradas con sufijo `_r2_`.

11. Botón "+ CTA" (2026-10-30, pedido del usuario): en cada bloque con CTA sugerida, build_site.py añade junto a "Abrir en X" un botón .xb "Abrir en X + CTA" (o "Citar en X + CTA" en citas; las respuestas no llevan CTA) cuyo texto es texto + "\n\n" + CTA (la primera opción entre comillas de la CTA sugerida; en citas se agrega después la URL de referencia). Mismo mecanismo: href https://x.com/intent/post?text=<quote(safe='')>, deep link iOS por el mismo listener. Si texto+CTA supera 280, muestra "+CTA: N caracteres". Automático para rutina, posts propios y memes. Backup: build_site.py.bak_precta.

12. TrendScout: build_site lee /workspace/trendscout_data.json en cada build y fusiona en $S/ts_store.json por id (incremental, sin duplicados; ids de tarjeta "ts-<id>" estables, así los descartes siguen ocultos). Sección "TrendScout (investigación diaria)" tras crash+memes y antes de "Resto", por prioridad. Items nuevos entran con draft_en y "gráfico pendiente": generar visual 4:5 (mk_ts.py, un logo, alternar día/noche), y poner image/theme/text_ext (EN ≥500 car., solo hechos del ítem) en ts_store.json. Backup: build_site.py.bak_prets.

13. FILTRO VIRAL (2026-11-02, backup *.bak_pre1102): poster_select.json {updated (debe = poster_data.updated), show:[urls en orden], warn:{url:nota}} → hits fuera de show van a "Omitidos"; los mostrados usan viral.optimized_version + hook_options (★). ts_store: campos hidden (motivo → Omitidos), hooks_show, verify (⚠️). memes_store.json = registro de memes publicados por fecha (order, memes[id,image,text,alt,cta,viral,verify,hooks]); imágenes images/meme_YYYYMMDD_0N.jpg. today.json {title,note,keys} = sección superior "Lo mejor de hoy" en orden de potencial (mezcla fuentes). Gráficos del día: /workspace/charts/mk_ts_1102.py (card() de mk_ts, un logo).

14. 3 HOOKS POR IDEA (2026-11-02, pedido del usuario; backup *.bak_pre3hooks): $S/hooks3.json {card_key:{hooks:[3, en inglés, emoción en 8-12 palabras + emoji], star:0, body:"info+takeaway+pregunta", warn, cta}}. build_site renderiza 3 bloques "★ Hook 1 / Hook 2 / Hook 3 · post armado" = hook+"\n\n"+body, cada uno con su Copiar texto, Abrir en X y "+ CTA". Sin entrada en hooks3: si la tarjeta tiene ≥3 hooks se usan 3 (★ primero) con body = post sin su primer párrafo. Quote/Reply (ideas ajenas, idioma del original) sin hooks. Memes: hooks v2 de Comedian (captions.md) en hooks3 y memes_store.
15. NUNCA OMITIR (2026-11-02): no existe sección "Omitidos". Hits fuera de show (poster_select), off_niche, ilegibles y ts hidden se muestran al final en "Ideas con menor potencial", marcados ⚠️, con 3 hooks e imagen.
16. SIN "gráfico pendiente" (2026-11-02): toda tarjeta lleva imagen. Serie real pública si existe (p. ej. Farside: /workspace/charts/mk_1102b.py bars()), si no, tarjeta de cifras clave card() con datos del propio post; ambos temas, alternar.

17. Conversaciones de interés (2026-11-09): página aparte en `conversaciones/index.html` → https://cemedinan.github.io/forecastquant-posts/conversaciones/ . `index.html` solo muestra el botón «Abrir conversaciones» (marcadores `powerlaw-conversations`). El resto de tarjetas de la principal no se toca. La página de conversaciones enlaza de vuelta a `../index.html`.

Reglas que no cambian: solo posts originales con `created_at` verificado y antigüedad ≤ 7200 segundos respecto del momento de la actualización, y `followers_count` entero verificado (`followers_count_verified: true`, con `followers_checked_at`) estrictamente mayor que 20000. La antigüedad sale de la creación del post, no de una cita ni de `searched_at`. Un conteo ausente, no verificado o ≤ 20000 no entra. Una marca de verificación no sustituye el número. La ventana no se amplía para completar cupos. Los que quedan fuera se archivan en `powerlaw_store.json` (`discarded` / `history`) sin el texto de la respuesta, y no se renderizan. Dedup por id del post original. Nada se publica solo: no hay llamada a la API de X.

Cada tarjeta: tema, autor, enlace al post original, hora Chile, contexto, respuesta en el idioma del post (editable y copiable). «Responder con sugerencia» es `https://x.com/intent/post?in_reply_to=ID&text=...`. «Responder en blanco» es el mismo id sin parámetro `text`. Si no queda nadie dentro de la ventana, la página lo dice y no rellena con cuentas chicas. Un modelo no es una garantía.

`build_site.py` sigue llamando a `inject_into_page(..., repo_dir=repo)`. Eso reescribe el enlace en `index.html` y vuelve a generar `conversaciones/index.html` en el mismo repo. No borra la carpeta `conversaciones/`.

Cuatro pasadas al día, desde la raíz del repo. `--index` sigue siendo la página principal; la de conversaciones se escribe al lado, en `conversaciones/index.html` (o en `--page`, si hace falta otra ruta).

```
python3 generator/update_powerlaw.py --revalidate --index index.html
python3 generator/update_powerlaw.py generator/inbox/opportunities_YYYYMMDD.json --index index.html
```

La segunda forma ya revalida la ventana; `--revalidate` solo hace falta cuando no hay lote nuevo. Sigue valiendo el orden viejo de dos posicionales: `python3 generator/update_powerlaw.py <lote.json> <index.html>`.

### Agregar un tema

Editar `generator/conversation_topics.json`. Es una lista. Cada objeto tiene:

- `id`: minúsculas, números y guiones (`etf`, `mineros`). Es el `data-topic` de la tarjeta y no se cambia después: las tarjetas ya guardadas lo usan.
- `label`: texto del filtro y del encabezado, en español.
- `keywords`: lista de frases. Si el lote no trae `topic`, gana la primera frase que aparezca (sin importar mayúsculas) en `context` o en `suggested_text`. Los temas más específicos van primero.
- `default`: exactamente uno en `true`. Es el tema si ninguna palabra clave calza y el lote no trae un id conocido.

Ejemplo para sumar mineros, sin tocar Python:

```json
{
  "id": "mineros",
  "label": "Mineros",
  "keywords": ["hashrate", "miner"]
}
```

En el JSON del lote, se puede fijar el tema y saltear las palabras clave:

```json
"topic": "mineros"
```

Un `topic` que no esté en la lista no crea una sección: la tarjeta cae en las palabras clave o en el tema default. Al correr `update_powerlaw.py`, el filtro y las secciones salen solos de esa lista. Hoy la lista es `power-law` (Power law de Bitcoin) y `precio-btc` (Debate del precio de BTC, default).
