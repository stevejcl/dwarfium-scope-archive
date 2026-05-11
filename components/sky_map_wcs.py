"""
components/sky_map_wcs.py — Sky Map overlay for all solved WCS sessions.
Opens Aladin Lite in the external browser via a NiceGUI HTTP route.
"""

import asyncio
import json
import math
import re
import time
import os
import webbrowser
from nicegui import ui, app
from components.i18n import t
from api.image_preview import build_preview_url, set_base_folder
from api.dwarf_backup_fct import get_session_file_ref

_DWARF_FOV = {
    2.75: (3856, 2180),
    3.01: (3840, 2160),
    4.03: (1920, 1080),
    5.98: (1928, 1096),
    6.02: (1920, 1080),
}


def _image_size_from_plate_scale(plate_scale):
    if plate_scale is None:
        return None, None
    best = min(_DWARF_FOV.keys(), key=lambda k: abs(k - plate_scale))
    if abs(best - plate_scale) < 0.5:
        return _DWARF_FOV[best]
    return None, None


def _footprint_corners(ra, dec, plate_scale, orientation):
    if ra is None or dec is None:
        return None
    if plate_scale is None:
        d = 0.5
        return [[ra-d, dec-d], [ra+d, dec-d], [ra+d, dec+d], [ra-d, dec+d]]
    w_px, h_px = _image_size_from_plate_scale(plate_scale)
    if not w_px:
        w_px, h_px = 3840, 2160
    hw = (plate_scale * w_px / 2.0) / 3600.0
    hh = (plate_scale * h_px / 2.0) / 3600.0
    ang = math.radians(orientation or 0.0)
    cos_a, sin_a = math.cos(ang), math.sin(ang)
    cos_dec = math.cos(math.radians(dec)) or 1e-9
    sky = []
    for dx, dy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        sky.append([ra + rx / cos_dec, dec + ry])
    return sky


def _load_wcs_sessions(conn):
    return conn.execute("""
        SELECT
            sw.entry_type,
            sw.entry_id,
            sw.panel_num,
            sw.ra_center,
            sw.dec_center,
            sw.plate_scale,
            sw.orientation,
            sw.solver,
            sw.solved_at,
            COALESCE(ao_b.name, ao_m.name, 'Unknown')           AS obj_name,
            COALESCE(be.session_dir, me.session_dir, '')          AS session_dir,
            COALESCE(sq.quality_score, 0)                         AS quality_score,
            CASE
              WHEN sw.entry_type = 'backup'
              THEN bd.location || '/' || dd.file_path
              ELSE ms.jpeg_path
            END                                                    AS image_path,
            CASE
              WHEN sw.entry_type = 'backup'
              THEN bd.location
              ELSE ms.jpeg_path
            END                                                    AS location,
            sw.crval1, sw.crval2,
            sw.cd1_1, sw.cd1_2, sw.cd2_1, sw.cd2_2,
            sw.crpix1, sw.crpix2,
            COALESCE(dw.name, 'Unknown')                       AS dwarf_name
        FROM SessionWCS sw
        LEFT JOIN BackupEntry        be   ON sw.entry_type = 'backup' AND sw.entry_id = be.id
        LEFT JOIN DwarfData          dd   ON be.dwarf_data_id = dd.id
        LEFT JOIN BackupDrive        bd   ON be.backup_drive_id = bd.id
        LEFT JOIN AstroObject        ao_b ON be.astro_object_id = ao_b.id
        LEFT JOIN SessionQuality     sq   ON be.id = sq.backup_entry_id
        LEFT JOIN Dwarf              dw   ON be.dwarf_id = dw.id
        LEFT JOIN ManualSessionEntry me   ON sw.entry_type = 'manual' AND sw.entry_id = me.id
        LEFT JOIN ManualSession      ms   ON me.manual_session_id = ms.id
        LEFT JOIN AstroObject        ao_m ON me.astro_object_id = ao_m.id
        ORDER BY sw.entry_id, sw.panel_num
    """).fetchall()


def _quality_color(score):
    if not score:    return '#888888'
    if score >= 80:  return '#22c55e'
    if score >= 65:  return '#f59e0b'
    return '#ef4444'


def _strip_dwarf_prefix(s):
    for pfx in ('RESTACKED_DWARF_RAW_TELE_MOSAIC_', 'RESTACKED_DWARF_RAW_WIDE_MOSAIC_',
                'RESTACKED_DWARF_RAW_TELE_', 'RESTACKED_DWARF_RAW_WIDE_',
                'DWARF_RAW_TELE_MOSAIC_', 'DWARF_RAW_WIDE_MOSAIC_',
                'DWARF_RAW_TELE_', 'DWARF_RAW_WIDE_'):
        if s.upper().startswith(pfx):
            return s[len(pfx):]
    return s


def _bbox_from_panel_rows(panel_rows):
    """
    Calculer le bounding box englobant depuis les WCS de panels individuels en DB.
    panel_rows : liste de tuples (ra, dec, plate_scale, orientation) pour panel_num > 0.
    Retourne (corners, ra_center, dec_center) ou (None, None, None).
    """
    all_ra  = []
    all_dec = []
    for (ra, dec, ps, orient, *_) in panel_rows:
        corners = _footprint_corners(ra, dec, ps, orient)
        if corners:
            all_ra.extend(c[0] for c in corners)
            all_dec.extend(c[1] for c in corners)

    if not all_ra:
        return None, None, None

    # Wrap-around fix : si certains coins sont près de 0° et d'autres près de 360°
    if max(all_ra) - min(all_ra) > 180:
        all_ra = [ra + 360 if ra < 180 else ra for ra in all_ra]

    ra_min, ra_max   = min(all_ra),  max(all_ra)
    dec_min, dec_max = min(all_dec), max(all_dec)
    ra_c  = ((ra_min + ra_max) / 2) % 360
    dec_c = (dec_min + dec_max) / 2
    # Ramener les coins dans 0-360
    bbox  = [[ra % 360, dec] for ra, dec in
             [[ra_min, dec_min], [ra_max, dec_min],
              [ra_max, dec_max], [ra_min, dec_max]]]
    return bbox, round(ra_c, 4), round(dec_c, 4)



def _get_server_url():
    try:
        port = (getattr(app, '_port', None)
                or app.storage.general.get('LAN_PORT', None)
                or app.storage.general.get('PORT', None)
                or 8000)
        scheme = 'https' if app.storage.general.get('HTTPS', False) else 'http'
        return scheme + '://127.0.0.1:' + str(port)
    except Exception:
        return 'http://127.0.0.1:8000'


def _build_aladin_html(footprints, ra_mean, dec_mean, server_url):
    target = str(round(float(ra_mean), 4)) + ' ' + str(round(float(dec_mean), 4))
    srv    = json.dumps(server_url)

    # ── CSS ───────────────────────────────────────────────────────────────────
    css  = 'body{margin:0;background:#111;font-family:sans-serif}\n'
    css += '#info{position:fixed;bottom:8px;left:50%;transform:translateX(-50%);z-index:999;'
    css += 'background:rgba(0,0,0,.7);color:#aaa;padding:4px 12px;'
    css += 'border-radius:6px;font-size:11px;pointer-events:none;white-space:nowrap}\n'
    css += '#toolbar{position:fixed;top:8px;left:50%;transform:translateX(-50%);'
    css += 'z-index:999;display:flex;gap:6px;align-items:center;'
    css += 'background:rgba(20,20,40,.85);padding:5px 8px;border-radius:8px;'
    css += 'border:1px solid #444;box-shadow:0 2px 10px rgba(0,0,0,.6)}\n'
    css += '#search-input{background:rgba(255,255,255,.1);color:#fff;border:1px solid #555;'
    css += 'border-radius:5px;padding:4px 10px;font-size:13px;width:200px;outline:none}\n'
    css += '#search-input::placeholder{color:#888}\n'
    css += '#search-input:focus{border-color:#888;background:rgba(255,255,255,.15)}\n'
    css += '#toolbar button{background:transparent;color:#ddd;border:1px solid #555;'
    css += 'border-radius:5px;padding:4px 10px;cursor:pointer;font-size:13px;white-space:nowrap}\n'
    css += '#toolbar button:hover{background:rgba(255,255,255,.15);color:#fff}\n'
    css += '#session-list{position:fixed;top:52px;left:50%;transform:translateX(-50%);z-index:999;'
    css += 'background:#1a1a2e;color:#e0e0e0;border:1px solid #444;'
    css += 'border-radius:8px;padding:10px;max-height:75vh;overflow-y:auto;'
    css += 'width:360px;display:none;font-size:12px;'
    css += 'box-shadow:0 4px 20px rgba(0,0,0,.8)}\n'
    css += '.s-item{padding:5px 8px;cursor:pointer;border-radius:4px;'
    css += 'margin-bottom:2px;display:flex;align-items:center;gap:8px;'
    css += 'border-left:3px solid transparent}\n'
    css += '.s-item:hover{background:#2a2a4e}\n'
    css += '.s-dot{width:10px;height:10px;border-radius:2px;flex-shrink:0}\n'
    css += '.s-name{font-weight:bold;color:#eee}\n'
    css += '.s-meta{color:#888;font-size:11px;margin-top:1px}\n'

    # ── JavaScript ────────────────────────────────────────────────────────────
    js  = 'var SERVER=' + srv + ';\n'
    js += 'var SD={};\n'
    js += 'var AL=null;\n'
    js += 'var _globalOv=null;\n'
    js += 'var _popupJustOpened=false;\n'
    js += 'var _loaded=0;\n'
    js += 'var _total=0;\n'

    js += 'function _updateProgress(){\n'
    js += '  var el=document.getElementById("info");\n'
    js += '  if(el&&_total>0)el.textContent=_loaded+" / "+_total+" sessions";\n'
    js += '}\n'

    js += 'var _selectOv=null;\n'
    js += 'var _imgRotation=0;\n'
    js += 'var _dwarfCats={};\n'
    js += 'function _getOrCreateCat(dwarfName){\n'
    js += '  if(!AL)return null;\n'
    js += '  if(_dwarfCats[dwarfName])return _dwarfCats[dwarfName];\n'
    js += '  var cat=A.catalog({name:dwarfName,sourceSize:18,shape:"square",\n'
    js += '    onClick:function(src){\n'
    js += '      var ra=src.ra,dec=src.dec;\n'
    js += '      var hits=_findAllAt(ra,dec);\n'
    js += '      if(hits.length<=1){showPopup(src.data._idx);}\n'
    js += '      else{showMultiPopup(hits,ra,dec);}\n'
    js += '    }});\n'
    js += '  AL.addCatalog(cat);\n'
    js += '  _dwarfCats[dwarfName]=cat;\n'
    js += '  return cat;\n'
    js += '}\n'

    js += 'function _highlightFootprint(f){\n'
    js += '  if(_selectOv&&AL){AL.removeOverlay(_selectOv);_selectOv=null;}\n'
    js += '  _selectOv=A.graphicOverlay({name:"selection",lineWidth:3});\n'
    js += '  AL.addOverlay(_selectOv);\n'
    js += '  _selectOv.add(A.polygon(f.corners,{color:"#00e5ff",fillColor:"#00e5ff",fillOpacity:0.15,lineWidth:3}));\n'
    js += '}\n'

    js += 'function loadImg(i){\n'
    js += '  var f=SD[i];\n'
    js += '  if(!f||!f.img_url||!AL)return;\n'
    js += '  document.getElementById("dw-popup").style.display="none";\n'
    js += '  _highlightFootprint(f);\n'
    js += '  var setUrl=SERVER+"/skymap_setbase?base="+encodeURIComponent(f.base_folder);\n'
    js += '  fetch(setUrl).then(function(){\n'
    js += '    var imgUrl=SERVER+f.img_url;\n'
    js += '    AL.gotoRaDec(f.ra,f.dec);\n'
    js += '    var fov;\n'
    js += '    if(f.is_mosaic){\n'
    js += '      var ras=f.corners.map(function(c){return c[0];});\n'
    js += '      var decs=f.corners.map(function(c){return c[1];});\n'
    js += '      var dRa=Math.max.apply(null,ras)-Math.min.apply(null,ras);\n'
    js += '      var dDec=Math.max.apply(null,decs)-Math.min.apply(null,decs);\n'
    js += '      fov=Math.max(dRa,dDec)*1.3;\n'
    js += '    }else{\n'
    js += '      fov=f.scale?parseFloat(f.scale)*f.naxis1/3600:1.5;\n'
    js += '      fov=fov*1.2;\n'
    js += '    }\n'
    js += '    AL.setFov(fov);\n'
    js += '    _imgRotation=0;\n'
    js += '    _showImgPanel(f,imgUrl);\n'
    js += '  });\n'
    js += '}\n'

    js += 'var _previewZoom=400;\n'
    js += 'function _showImgPanel(f,imgUrl){\n'
    js += '  _previewZoom=400;\n'
    js += '  var ov=document.getElementById("dw-img-overlay");\n'
    js += '  if(!ov){ov=document.createElement("div");ov.id="dw-img-overlay";document.body.appendChild(ov);}\n'
    js += '  var closeBtn="<span onclick=\'document.getElementById(\\"dw-img-overlay\\").style.display=\\"none\\";if(window._selectOv){AL.removeOverlay(_selectOv);_selectOv=null;}\'"\n'
    js += '    +" style=\'cursor:pointer;color:#aaa;font-size:18px;padding-left:10px\'>X</span>";\n'
    js += '  var rotBtn="<span onclick=\'_imgRotation=(_imgRotation+90)%360;var img=document.getElementById(\\"preview-img\\");if(img)img.style.transform=\\"rotate(\\"+_imgRotation+\\"deg)\\";\'"\n'
    js += '    +" style=\'cursor:pointer;color:#aaa;font-size:16px;padding-left:8px;user-select:none\' title=\'Rotate 90°\'>&#8635;</span>";\n'
    js += '  var zoomInBtn="<span onclick=\'_previewZoom=Math.min(_previewZoom+150,1200);var img=document.getElementById(\\"preview-img\\");if(img){img.style.width=_previewZoom+\\"px\\";img.style.maxHeight=\\"\\";}\'"\n'
    js += '    +" style=\'cursor:pointer;color:#aaa;font-size:18px;padding-left:8px;user-select:none\' title=\'Zoom in\'>+</span>";\n'
    js += '  var zoomOutBtn="<span onclick=\'_previewZoom=Math.max(_previewZoom-150,200);var img=document.getElementById(\\"preview-img\\");if(img){img.style.width=_previewZoom+\\"px\\";img.style.maxHeight=\\"\\";}\'"\n'
    js += '    +" style=\'cursor:pointer;color:#aaa;font-size:18px;padding-left:8px;user-select:none\' title=\'Zoom out\'>&#8722;</span>";\n'
    js += '  var header="<div style=\'display:flex;justify-content:space-between;align-items:center;margin-bottom:6px\'>"\n'
    js += '    +"<span style=\'color:"+f.color+";font-size:13px;font-weight:bold\'>"+f.label+"</span>"\n'
    js += '    +"<span>"+zoomOutBtn+zoomInBtn+rotBtn+closeBtn+"</span></div>";\n'
    js += '  var img=document.createElement("img");\n'
    js += '  img.id="preview-img";\n'
    js += '  img.src=imgUrl;\n'
    js += '  img.style.cssText="width:400px;object-fit:contain;border-radius:4px;display:block;transition:width 0.15s;";\n'
    js += '  img.onerror=function(){this.alt="Image not available";};\n'
    js += '  ov.style.cssText="position:fixed;bottom:10px;right:10px;z-index:8000;overflow:auto;max-height:90vh;"\n'
    js += '    +"background:#1a1a2e;border:2px solid "+f.color+";border-radius:8px;"\n'
    js += '    +"padding:8px;max-width:95vw;box-shadow:0 4px 16px rgba(0,0,0,.8)";\n'
    js += '  ov.innerHTML=header;\n'
    js += '  ov.appendChild(img);\n'
    js += '  ov.style.display="block";\n'
    js += '}\n'

    js += 'function closePopup(){\n'
    js += '  document.getElementById("dw-popup").style.display="none";\n'
    js += '  if(_selectOv&&AL){AL.removeOverlay(_selectOv);_selectOv=null;}\n'
    js += '}\n'

    js += 'function showPopup(i){\n'
    js += '  _popupJustOpened=true;\n'
    js += '  var f=SD[i];\n'
    js += '  _highlightFootprint(f);\n'
    js += '  var pop=document.getElementById("dw-popup");\n'
    js += '  var panels=f.n_panels?(" ("+f.n_panels+" panels)"):" ";\n'
    js += '  var btn=f.img_url\n'
    js += '    ? "<button onclick=\\"loadImg("+i+")\\" style=\\"margin-top:10px;width:100%;"\n'
    js += '      +"padding:6px;background:"+f.color+";color:#fff;border:none;"\n'
    js += '      +"border-radius:6px;cursor:pointer;font-size:13px\\">Show image</button>"\n'
    js += '    : "<p style=\\"color:#888;font-size:12px;margin-top:8px\\">No image</p>";\n'
    js += '  pop.innerHTML=\n'
    js += '    "<div style=\'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);"\n'
    js += '    +"background:#1a1a2e;color:#e0e0e0;border:2px solid "+f.color+";"\n'
    js += '    +"border-radius:10px;padding:16px 20px;min-width:280px;"\n'
    js += '    +"box-shadow:0 4px 24px rgba(0,0,0,.8);z-index:9999;font-family:sans-serif\'>"\n'
    js += '    +"<div style=\'display:flex;justify-content:space-between;align-items:center;margin-bottom:10px\'>"\n'
    js += '    +"<b style=\'color:"+f.color+"\'>"+f.label+panels+"</b>"\n'
    js += '    +"<span onclick=\'closePopup()\' style=\'cursor:pointer;font-size:20px;color:#aaa;padding-left:12px\'>X</span>"\n'
    js += '    +"</div>"\n'
    js += '    +"<table style=\'width:100%;font-size:13px\'>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>RA</td><td style=\'color:#fff\'>"+f.ra+"</td></tr>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>DEC</td><td style=\'color:#fff\'>"+f.dec+"</td></tr>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>Scale</td><td style=\'color:#fff\'>"+f.scale+"</td></tr>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>Solver</td><td style=\'color:#fff\'>"+f.solver+"</td></tr>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>Solved</td><td style=\'color:#fff\'>"+f.solved_at+"</td></tr>"\n'
    js += '    +"<tr><td style=\'color:#aaa;padding:2px 8px 2px 0\'>Quality</td><td style=\'color:#fff\'>"+(f.score||"N/A")+"</td></tr>"\n'
    js += '    +"</table>"+btn+"</div>";\n'
    js += '  pop.style.display="block";\n'
    js += '}\n'

    js += 'function _raInView(ra,raC,fovRa){\n'
    js += '  var d=Math.abs(ra-raC);if(d>180)d=360-d;return d<fovRa/2;\n'
    js += '}\n'

    js += 'function showVisibleSessions(){\n'
    js += '  if(!AL)return;\n'
    js += '  var center=AL.getRaDec(),fov=AL.getFov();\n'
    js += '  var raC=center[0],decC=center[1],fovRa=fov[0],fovDec=fov[1];\n'
    js += '  var visible=[];\n'
    js += '  for(var i in SD){\n'
    js += '    var f=SD[i];\n'
    js += '    if(_raInView(f.ra,raC,fovRa*1.5)&&Math.abs(f.dec-decC)<fovDec*1.5)\n'
    js += '      visible.push({i:parseInt(i),f:f});\n'
    js += '  }\n'
    js += '  visible.sort(function(a,b){return b.f.score-a.f.score;});\n'
    js += '  var list=document.getElementById("session-list");\n'
    js += '  if(visible.length===0){\n'
    js += '    list.innerHTML="<div style=\'padding:8px;color:#888\'>No sessions in current view</div>";\n'
    js += '  }else{\n'
    js += '    var html="<div style=\'font-weight:bold;margin-bottom:8px;color:#aaa;border-bottom:1px solid #333;padding-bottom:6px\'>"\n'
    js += '      +visible.length+" sessions in view</div>";\n'
    js += '    visible.forEach(function(v){\n'
    js += '      var c=v.f.color;\n'
    js += '      var panels=v.f.n_panels?(" ("+v.f.n_panels+"p)"):" ";\n'
    js += '      html+="<div class=\'s-item\' style=\'border-left-color:"+c+"\' "\n'
    js += '        +"onclick=\'showPopup("+v.i+");document.getElementById(\\"session-list\\").style.display=\\"none\\";\'>"\n'
    js += '        +"<div class=\'s-dot\' style=\'background:"+c+"\'></div>"\n'
    js += '        +"<div><div class=\'s-name\'>"+v.f.label+panels+"</div>"\n'
    js += '        +"<div class=\'s-meta\'>Q:"+(v.f.score||"?")+" | "+v.f.solver+" | "+v.f.solved_at+"</div>"\n'
    js += '        +"</div></div>";\n'
    js += '    });\n'
    js += '    list.innerHTML=html;\n'
    js += '  }\n'
    js += '  list.style.display="block";\n'
    js += '}\n'

    js += 'function _pointInPolygon(ra,dec,corners){\n'
    js += '  var inside=false,n=corners.length;\n'
    js += '  for(var i=0,j=n-1;i<n;j=i++){\n'
    js += '    var xi=corners[i][0],yi=corners[i][1];\n'
    js += '    var xj=corners[j][0],yj=corners[j][1];\n'
    js += '    if(((yi>dec)!=(yj>dec))&&(ra<(xj-xi)*(dec-yi)/(yj-yi)+xi))inside=!inside;\n'
    js += '  }\n'
    js += '  return inside;\n'
    js += '}\n'

    js += 'function _findAllAt(ra,dec){\n'
    js += '  var hits=[];\n'
    js += '  for(var i=0;i<SD.length;i++){\n'
    js += '    if(SD[i]&&_pointInPolygon(ra,dec,SD[i].corners))hits.push(i);\n'
    js += '  }\n'
    js += '  return hits;\n'
    js += '}\n'

    js += 'function showMultiPopup(hits,ra,dec){\n'
    js += '  var pop=document.getElementById("dw-popup");\n'
    js += '  var html="<div style=\'font-weight:bold;color:#aaa;margin-bottom:8px;border-bottom:1px solid #333;padding-bottom:6px\'>"\n'
    js += '    +hits.length+" sessions at this location — click one:</div>";\n'
    js += '  hits.forEach(function(i){\n'
    js += '    var f=SD[i];\n'
    js += '    var panels=f.n_panels>1?" ("+f.n_panels+"p)":"";\n'
    js += '    html+="<div class=\'s-item\' style=\'border-left-color:"+f.color+";cursor:pointer\' "\n'
    js += '      +"onclick=\'showPopup("+i+");\'>"\n'
    js += '      +"<div class=\'s-dot\' style=\'background:"+f.color+"\'></div>"\n'
    js += '      +"<div><div class=\'s-name\'>"+f.label+panels+"</div>"\n'
    js += '      +"<div class=\'s-meta\'>Q:"+(f.score||"?")+" | "+f.solver+" | "+f.solved_at+"</div>"\n'
    js += '      +"</div></div>";\n'
    js += '  });\n'
    js += '  var closeBtn="<div style=\'text-align:right;margin-top:8px\'><span onclick=\'closePopup()\' "\n'
    js += '    +"style=\'cursor:pointer;color:#888;font-size:12px\'>✕ Close</span></div>";\n'
    js += '  pop.innerHTML=html+closeBtn;\n'
    js += '  var px=AL.world2pix(ra,dec);\n'
    js += '  if(px){pop.style.left=Math.min(px[0]+10,window.innerWidth-320)+"px";pop.style.top=Math.min(px[1]+10,window.innerHeight-200)+"px";}\n'
    js += '  pop.style.display="block";\n'
    js += '  _popupJustOpened=true;\n'
    js += '}\n'

    js += 'function _addFootprint(fp,idx,al){\n'
    js += '  SD[idx]=fp;\n'
    js += '  _globalOv.add(A.polygon(fp.corners,{color:fp.color,fillColor:fp.color,fillOpacity:0.15,lineWidth:2}));\n'
    js += '  (function(i){\n'
    js += '    try{\n'
    js += '      var cat=_getOrCreateCat(fp.dwarf_name||"Unknown");\n'
    js += '      if(cat)cat.addSources([A.source(fp.ra,fp.dec,{name:fp.label,_idx:i})]);\n'
    js += '    }catch(e){console.warn("catalog error",e);}\n'
    js += '  })(idx);\n'
    js += '  _loaded++;\n'
    js += '  _updateProgress();\n'
    js += '}\n'

    js += 'function _loadBatch(fps,start,al){\n'
    js += '  var end=Math.min(start+40,fps.length);\n'
    js += '  for(var i=start;i<end;i++){_addFootprint(fps[i],i,al);}\n'
    js += '  if(end<fps.length){setTimeout(function(){_loadBatch(fps,end,al);},50);}\n'
    js += '}\n'

    js += 'function initAL(){\n'
    js += '  if(typeof A==="undefined"){setTimeout(initAL,200);return;}\n'
    js += '  A.init.then(function(){\n'
    js += '    var al=A.aladin("#aladin-lite-div",{\n'
    js += '      survey:"P/DSS2/color",fov:180,target:"' + target + '",\n'
    js += '      showReticle:false,showZoomControl:true,\n'
    js += '      showFullscreenControl:true,showLayersControl:true,\n'
    js += '      backgroundColor:"#111111"\n'
    js += '    });\n'
    js += '    AL=al;\n'
    js += '    _globalOv=A.graphicOverlay({name:"sessions",lineWidth:2});\n'
    js += '    al.addOverlay(_globalOv);\n'
    js += '    al.aladinDiv.addEventListener("click",function(e){\n'
    js += '      if(_popupJustOpened){_popupJustOpened=false;return;}\n'
    js += '      if(!e.target.closest("#dw-popup"))closePopup();\n'
    js += '    });\n'
    js += '    document.getElementById("info").textContent="Loading...";\n'
    js += '    fetch(SERVER+"/skymap_data").then(function(r){return r.json();})\n'
    js += '    .then(function(fps){\n'
    js += '      _total=fps.length;\n'
    js += '      _loadBatch(fps,0,al);\n'
    js += '    }).catch(function(e){\n'
    js += '      document.getElementById("info").textContent="Error: "+e;\n'
    js += '    });\n'
    js += '  }).catch(function(e){\n'
    js += '    document.getElementById("aladin-lite-div").innerHTML=\n'
    js += '      "<div style=\'padding:40px;color:#ef4444\'>Error: "+e+"</div>";\n'
    js += '  });\n'
    js += '}\n'

    js += 'function _bindButtons(){\n'
    js += '  document.getElementById("btn-sessions").addEventListener("click",showVisibleSessions);\n'
    js += '  document.getElementById("btn-close-list").addEventListener("click",function(){\n'
    js += '    document.getElementById("session-list").style.display="none";\n'
    js += '  });\n'
    js += '  document.getElementById("btn-search").addEventListener("click",function(){\n'
    js += '    var q=document.getElementById("search-input").value.trim();\n'
    js += '    if(q&&AL){AL.gotoObject(q);}\n'
    js += '  });\n'
    js += '  document.getElementById("search-input").addEventListener("keydown",function(e){\n'
    js += '    if(e.key==="Enter"){var q=this.value.trim();if(q&&AL)AL.gotoObject(q);}\n'
    js += '  });\n'
    js += '}\n'
    js += 'if(document.readyState==="loading"){\n'
    js += '  document.addEventListener("DOMContentLoaded",function(){_bindButtons();initAL();});\n'
    js += '}else{_bindButtons();initAL();}\n'

    # ── HTML ──────────────────────────────────────────────────────────────────
    html  = '<!DOCTYPE html>\n<html>\n<head>\n'
    html += '<meta charset="utf-8"/>\n'
    html += '<title>Dwarfium Sky Map</title>\n'
    html += '<link rel="stylesheet" href="https://aladin.u-strasbg.fr/AladinLite/api/v3/latest/aladin.min.css"/>\n'
    html += '<script src="https://aladin.u-strasbg.fr/AladinLite/api/v3/latest/aladin.js" charset="utf-8"><' + '/script>\n'
    html += '<style>\n' + css + '</style>\n'
    html += '</head>\n<body>\n'
    html += '<div id="info">Loading...</div>\n'
    html += '<div id="toolbar">\n'
    html += '  <input id="search-input" type="text" placeholder="Search object..."/>\n'
    html += '  <button id="btn-search">&#128269;</button>\n'
    html += '  <button id="btn-sessions">&#9776; Sessions in view</button>\n'
    html += '  <button id="btn-close-list">&#x2715;</button>\n'
    html += '</div>\n'
    html += '<div id="session-list"></div>\n'
    html += '<div id="dw-popup" style="display:none"></div>\n'
    html += '<div id="aladin-lite-div" style="width:100vw;height:100vh;"></div>\n'
    html += '<script>\n' + js + '\n<' + '/script>\n'
    html += '</body>\n</html>\n'
    return html


def _register_skymap_route(footprints, ra_mean, dec_mean, server_url):
    from fastapi import Response, Query
    from fastapi.responses import JSONResponse

    html  = _build_aladin_html(footprints, ra_mean, dec_mean, server_url)
    app.routes[:] = [r for r in app.routes
                      if getattr(r, 'path', '') not in
                      ('/skymap_view', '/skymap_setbase', '/skymap_data')]
    _html = html
    _fps  = footprints

    @app.get('/skymap_view', include_in_schema=False)
    async def skymap_view():
        return Response(
            content=_html, media_type='text/html',
            headers={'Cache-Control': 'no-store, no-cache, must-revalidate',
                     'Pragma': 'no-cache', 'Expires': '0'}
        )

    @app.get('/skymap_data', include_in_schema=False)
    async def skymap_data():
        return JSONResponse(content=_fps)

    @app.get('/skymap_setbase', include_in_schema=False)
    async def skymap_setbase(base: str = Query('')):
        if base:
            set_base_folder(base)
        return Response(content='ok', media_type='text/plain')


# ── NiceGUI component ─────────────────────────────────────────────────────────

def show_sky_map_wcs(conn=None, height='700px', limit=None):
    server_url = _get_server_url()

    # ── En-tête deux colonnes ────────────────────────────────────────────────
    with ui.row().classes('w-full items-start justify-between mb-1 gap-4'):
        # Gauche : légende qualité
        with ui.row().classes('gap-4 text-xs items-center'):
            for color, lbl in [('#22c55e', '>= 80'), ('#f59e0b', '65-79'),
                               ('#ef4444', '< 65'),  ('#888888', 'N/A')]:
                with ui.row().classes('items-center gap-1'):
                    ui.element('div').style(
                        'width:20px;height:20px;background:' + color + ';border-radius:3px'
                    )
                    ui.label(lbl)

        # Droite : bouton + hint
        with ui.column().classes('items-end gap-1'):
            open_btn = ui.button(
                t('sky_map_open_browser'),
                on_click=lambda: webbrowser.open(server_url + '/skymap_view?v=' + str(int(time.time())))
            ).props('color=primary unelevated size=md icon=travel_explore')
            open_btn.disable()
            ui.label(t('sky_map_open_hint')).classes('text-xs text-gray-500 italic')

    # ── Stats par Dwarf ───────────────────────────────────────────────────────
    def _load_dwarf_stats(min_q=60):
        from api.dwarf_backup_db import DB_NAME, connect_db, close_db
        c = connect_db(DB_NAME)
        rows = c.execute("""
            SELECT
                COALESCE(dw.name, 'Unknown')                              AS dwarf_name,
                COUNT(DISTINCT be.id)                                      AS total,
                COUNT(DISTINCT sw.entry_id)                                AS solved,
                COUNT(DISTINCT CASE WHEN sq.quality_score >= ? AND sw.entry_id IS NULL
                                     AND LOWER(COALESCE(ao.name, '')) NOT IN
                                         ('sun','moon','lune','soleil','jupiter','saturn',
                                          'saturne','mars','venus','mercury','mercure',
                                          'uranus','neptune')
                                    THEN be.id END)                        AS pending,
                COUNT(DISTINCT CASE WHEN sq.backup_entry_id IS NULL
                                    THEN be.id END)                        AS no_score
            FROM BackupEntry be
            LEFT JOIN Dwarf          dw  ON be.dwarf_id        = dw.id
            LEFT JOIN SessionQuality sq  ON sq.backup_entry_id = be.id
            LEFT JOIN AstroObject    ao  ON be.astro_object_id = ao.id
            LEFT JOIN SessionWCS     sw  ON sw.entry_type = 'backup'
                                        AND sw.entry_id   = be.id
                                        AND sw.panel_num  = 0
            GROUP BY dw.name
            ORDER BY dw.name
        """, (min_q,)).fetchall()
        close_db(c)
        return rows

    # ── Slider qualité + status sessions ─────────────────────────────────────
    with ui.row().classes('items-center gap-3 mt-2 mb-1 w-full justify-between'):
        with ui.row().classes('items-center gap-3'):
            ui.label(t('sky_map_min_quality')).classes('text-sm text-gray-400')
            quality_slider = ui.slider(min=0, max=100, value=60, step=5).classes('w-48')
            quality_val = ui.label('60').classes('text-sm font-bold w-8')
        with ui.row().classes('items-center gap-2'):
            spinner = ui.spinner(size='sm')
            status  = ui.label('Loading sessions...').classes('text-gray-400 italic text-sm')

    # ── Tableau Dwarf ─────────────────────────────────────────────────────────
    stats_rows = _load_dwarf_stats(60)

    scan_running = {'value': False}

    # ── Barre de progression scan (créée avant les boutons qui la référencent) ─
    with ui.row().classes('items-center gap-3 mt-3 w-full'):
        progress_bar = ui.linear_progress(value=0).classes('flex-1')
        progress_bar.set_visibility(False)
    progress_label = ui.label('').classes('text-sm text-gray-400 mt-1')
    progress_label.set_visibility(False)

    # Références aux labels pending pour mise à jour dynamique
    # { dwarf_name: (pending_label, scan_btn_ref) }
    _pending_labels = {}

    def _refresh_pending(min_q):
        fresh = {r[0]: r for r in _load_dwarf_stats(min_q)}
        for dname, (plbl, sbtn) in _pending_labels.items():
            row = fresh.get(dname)
            if row:
                _, _, _, new_pending, _ = row
                plbl.set_text(str(new_pending))
                plbl.classes(
                    remove='text-yellow-400 text-gray-500',
                    add='text-yellow-400' if new_pending > 0 else 'text-gray-500'
                )
                if new_pending > 0:
                    sbtn.props(remove='color=grey', add='color=primary')
                    sbtn.enable()
                else:
                    sbtn.props(remove='color=primary', add='color=grey')

    with ui.card().classes('w-full mt-2 p-0'):
        with ui.column().classes('w-full gap-0'):
            # Header
            with ui.row().classes('w-full px-4 py-2 bg-gray-800 text-xs text-gray-400 gap-2'):
                ui.label(t('sky_map_col_dwarf')).classes('w-40 text-sm')
                ui.label(t('sky_map_col_total')).classes('w-16 text-right text-sm')
                ui.label(t('sky_map_col_solved')).classes('w-20 text-right text-sm')
                ui.label(t('sky_map_col_pending')).classes('w-16 text-right text-sm')
                ui.label(t('sky_map_col_no_score')).classes('w-16 text-right text-sm')
                ui.label('').classes('flex-1')

            # Adaptive row height based on number of Dwarfs
            n_dwarfs = len(stats_rows)
            row_py = 'py-2' if n_dwarfs >= 6 else ('py-4' if n_dwarfs <= 2 else 'py-3')

            for (dwarf_name, total, solved, pending, no_score) in stats_rows:
                pct = int(solved / total * 100) if total else 0

                with ui.row().classes(f'w-full px-4 items-center gap-2 border-t border-gray-700 {row_py}'):
                    ui.label(dwarf_name).classes('w-40 text-base font-medium truncate')
                    ui.label(str(total)).classes('w-16 text-right text-base text-gray-300')

                    ui.label(f'{solved} ({pct}%)').classes('w-20 text-right text-base text-green-400')

                    pending_lbl = ui.label(str(pending)).classes(
                        'w-16 text-right text-base ' +
                        ('text-yellow-400' if pending > 0 else 'text-gray-500')
                    )

                    ui.label(str(no_score) if no_score else '—').classes(
                        'w-16 text-right text-base ' +
                        ('text-gray-400' if no_score else 'text-gray-600')
                    )

                    # Bouton scan
                    def _make_scan(dname=dwarf_name, plbl=pending_lbl):
                        async def _do_scan():
                            p = app.storage.general.get('scan_progress', {})
                            if p.get('status') == 'running':
                                ui.notify(f'Scan already running — {p.get("dwarf","")}', type='warning')
                                return
                            # Vérifier le lock file (scan CLI en cours)
                            import tempfile, os
                            lock_file = os.path.join(tempfile.gettempdir(), 'astrometry_scan.lock')
                            if os.path.exists(lock_file):
                                try:
                                    pid = int(open(lock_file).read().strip())
                                    import psutil
                                    if psutil.pid_exists(pid):
                                        ui.notify(f'Scan CLI already running (PID {pid}) — stop it first', type='warning')
                                        return
                                except Exception:
                                    pass  # stale lock
                            q = int(quality_slider.value)
                            # Clear any stale progress before starting
                            app.storage.general.pop('scan_progress', None)
                            app.storage.general.pop('scan_cancelled', None)
                            app.storage.general['scan_progress'] = {
                                'status': 'running',
                                'dwarf':  dname,
                                'quality': q,
                                'solved': 0,
                                'failed': 0,
                                'current': f'Starting scan for {dname}…',
                            }
                            # Lancer en background — survit à la navigation
                            from nicegui import background_tasks
                            _scan_timer.activate()
                            background_tasks.create(_bg_scan(dname, q))
                        return _do_scan

                    scan_btn = ui.button(t('sky_map_btn_scan'), on_click=_make_scan()) \
                        .props('size=sm color=primary unelevated') \
                        .classes('ml-auto')
                    if pending == 0:
                        scan_btn.props(add='color=grey')
                    _pending_labels[dwarf_name] = (pending_lbl, scan_btn)

    # ── Badge scan en cours + bouton Cancel ──────────────────────────────────
    with ui.row().classes('items-center gap-3 mt-1'):
        scan_badge = ui.label('') \
            .classes('text-sm font-medium text-orange-400 animate-pulse')
        scan_badge.set_visibility(False)

        def _cancel_scan():
            app.storage.general.pop('scan_progress', None)
            app.storage.general['scan_cancelled'] = True  # Signal background task to stop
            scan_badge.set_visibility(False)
            cancel_scan_btn.set_visibility(False)
            progress_label.set_text('⚠️  Scan cancelled')
            for _, (_, sbtn) in _pending_labels.items():
                try: sbtn.enable()
                except Exception: pass
            ui.notify('Scan cancelled', type='warning')

        cancel_scan_btn = ui.button('✕ Cancel scan', on_click=_cancel_scan) \
            .props('size=sm color=negative flat') \
            .classes('text-xs')
        cancel_scan_btn.set_visibility(False)

    # ── Background scan function (survit à la navigation) ────────────────────
    async def _bg_scan(dname, q):
        from nicegui import run
        from tools.astrometry_scan import get_sessions_to_solve, save_wcs, \
            find_image_for_session, extract_wcs_from_file, _solve_mosaic_panels, \
            detect_mosaic_restitched, _cleanup_temp, print_report
        from api.dwarf_backup_db import DB_NAME, connect_db, close_db
        from api.astrometry_resolver import auto_resolve, has_solve_field, has_astap
        from api.dwarf_backup_db_api import get_setting_text
        import tempfile as _tmp

        def _run():
            counts = {'solved': 0, 'failed': 0}

            def _update_progress(current=''):
                try:
                    import time as _t
                    app.storage.general['scan_progress'] = {
                        'status':      'running',
                        'dwarf':       dname,
                        'quality':     q,
                        'solved':      counts['solved'],
                        'failed':      counts['failed'],
                        'current':     current[:120],
                        'last_update': _t.time(),
                    }
                except Exception:
                    pass

            conn = connect_db(DB_NAME)
            try:
                api_key    = get_setting_text(conn, 'NOVA_ASTRO_API') or ''
                astap_db   = get_setting_text(conn, 'ASTAP_DB') or 'D50'

                # Fake args object
                class _Args:
                    date_from = date_to = session = re_solver = entry_type = None
                    force = False; exact = False; fix_null_ra = False
                    min_quality = q; max_quality = None; limit = 50
                    dwarf = dname; crop = False; crop_margin = 0.2
                    delay = 0; dry_run = False

                sessions = get_sessions_to_solve(
                    conn, None, None, False, q, 50,
                    dwarf_filter=dname,
                    entry_type='backup',
                )
                print(f'  [scan] {len(sessions)} session(s) to solve for {dname} (q>={q})', flush=True)
                print(f'  [scan] api_key={bool(api_key)} astap_db={astap_db} ASTAP_PATH={has_astap()}', flush=True)

                SKIP_OBJECTS = {'sun', 'moon', 'lune', 'soleil', 'jupiter', 'saturn',
                                'saturne', 'mars', 'venus', 'mercury', 'mercure',
                                'uranus', 'neptune', 'solar', 'solaire'}

                for session in sessions:
                    # Check cancellation flag
                    if app.storage.general.get('scan_cancelled'):
                        print(f'  [scan] cancelled by user', flush=True)
                        break

                    obj = (session.get('object_name') or '?')[:25]

                    # Skip solar system objects
                    if any(s in (session.get('object_name') or '').lower() for s in SKIP_OBJECTS):
                        print(f'  [scan] skip {obj} (solar system object)', flush=True)
                        continue

                    _update_progress(f'Solving {obj}…')
                    print(f'  [scan] {obj}', flush=True)

                    image_path, img_type = find_image_for_session(session)

                    is_mosaic, is_restitched, mosaic_folder, _ = detect_mosaic_restitched(session)

                    try:
                        if img_type == 'mosaic_panels':
                            _solve_mosaic_panels(conn, session, api_key, astap_db,
                                                 False, 0.2, 'auto')
                            # Count as solved only if at least one panel was resolved
                            n_solved = conn.execute("""
                                SELECT COUNT(*) FROM SessionWCS
                                WHERE entry_type=? AND entry_id=? AND panel_num > 0
                                  AND ra_center IS NOT NULL
                            """, (session['entry_type'], session['entry_id'])).fetchone()[0]
                            if n_solved > 0:
                                counts['solved'] += 1
                                _update_progress(f'✅ {obj} (mosaic {n_solved} panels)')
                                print(f'  [scan] ✅ {obj} ({n_solved} panels)', flush=True)
                            else:
                                counts['failed'] += 1
                                print(f'  [scan] ❌ {obj} (no panels resolved)', flush=True)
                        elif image_path:
                            wcs_file = auto_resolve(api_key, str(image_path), astap_db=astap_db)
                            wcs_data = extract_wcs_from_file(wcs_file)
                            if wcs_data and wcs_data.get('ra_center'):
                                solver = 'astap' if wcs_file.endswith('.ini') else 'nova'
                                save_wcs(conn, session, wcs_data, wcs_file, solver, panel_num=0)
                                counts['solved'] += 1
                                _update_progress(f'✅ {obj}')
                                print(f'  [scan] ✅ {obj} RA={wcs_data["ra_center"]:.4f}', flush=True)
                            else:
                                counts['failed'] += 1
                                print(f'  [scan] ❌ {obj}', flush=True)
                        else:
                            print(f'  [scan] skip {obj} (no image)', flush=True)
                    except Exception as e:
                        counts['failed'] += 1
                        print(f'  [scan] ❌ {obj}: {e}', flush=True)
                    finally:
                        if image_path:
                            _cleanup_temp(image_path)

            finally:
                close_db(conn)

            return counts['solved'], counts['failed']

        try:
            solved_n, failed_n = await run.io_bound(_run)
            app.storage.general['scan_progress'] = {
                'status':  'done',
                'dwarf':   dname,
                'quality': q,
                'solved':  solved_n,
                'failed':  failed_n,
                'current': f'Done — {solved_n} solved' + (f', {failed_n} failed' if failed_n else ''),
            }
        except Exception as e:
            # Cancelled or error — clean up storage
            print(f'[scan] _bg_scan ended: {e}', flush=True)
            p = app.storage.general.get('scan_progress', {})
            if p.get('status') == 'running':
                app.storage.general.pop('scan_progress', None)

    # ── Timer polling du storage → mise à jour UI ─────────────────────────────
    def _poll_scan():
        try:
            p = app.storage.general.get('scan_progress', {})
            if not p:
                scan_badge.set_visibility(False)
                progress_bar.set_visibility(False)
                return

            status  = p.get('status', '')
            dname   = p.get('dwarf', '')
            solved_n = p.get('solved', 0)
            failed_n = p.get('failed', 0)
            current = p.get('current', '')

            if status == 'running':
                # Stale scan detection — if last update > 10 min ago, clear it
                import time as _time
                last_update = p.get('last_update', _time.time())
                if _time.time() - last_update > 600:
                    app.storage.general.pop('scan_progress', None)
                    scan_badge.set_visibility(False)
                    cancel_scan_btn.set_visibility(False)
                    progress_label.set_text('⚠️  Previous scan timed out — cleared')
                    return
                scan_badge.set_text(f'🔄  Scan running — {dname} ({solved_n} solved)')
                scan_badge.set_visibility(True)
                cancel_scan_btn.set_visibility(True)
                progress_bar.set_visibility(True)
                progress_label.set_text(f'⏳  {current}')
                progress_label.set_visibility(True)
                # Désactiver tous les boutons scan
                for _, (_, sbtn) in _pending_labels.items():
                    try: sbtn.disable()
                    except Exception: pass

            elif status == 'done':
                scan_badge.set_visibility(False)
                cancel_scan_btn.set_visibility(False)
                progress_bar.set_value(1)
                progress_label.set_text(
                    f'✅  {dname}: {solved_n} solved' +
                    (f', {failed_n} failed' if failed_n else '')
                )
                ui.notify(
                    f'{dname}: {solved_n} solved' + (f', {failed_n} failed' if failed_n else ''),
                    type='positive' if solved_n > 0 else 'warning',
                    timeout=5000,
                )
                # Réactiver les boutons
                for _, (_, sbtn) in _pending_labels.items():
                    try: sbtn.enable()
                    except Exception: pass
                _refresh_pending(int(quality_slider.value))
                # Clear storage après affichage
                app.storage.general.pop('scan_progress', None)
                _scan_timer.deactivate()
                # Recharger la sky map
                import asyncio
                asyncio.ensure_future(_prepare())

        except Exception as e:
            print(f'[scan poll] {e}')

    _scan_timer = ui.timer(1.5, _poll_scan)

    # Initialiser les boutons avec la qualité par défaut
    _refresh_pending(60)

    # Restaurer état si scan en cours au chargement de la page
    p = app.storage.general.get('scan_progress', {})
    if p.get('status') == 'running':
        scan_badge.set_text(f'🔄  Scan running — {p.get("dwarf","")}')
        scan_badge.set_visibility(True)
        progress_bar.set_visibility(True)
        progress_label.set_text(f'⏳  {p.get("current","")}')
        progress_label.set_visibility(True)

    # ── Rafraîchir les pending selon qualité ──────────────────────────────────
    def _on_quality_change(e):
        q = int(e.args)
        quality_val.set_text(str(q))
        _refresh_pending(q)

    quality_slider.on('update:model-value', _on_quality_change)

    # ── Calcul en arrière-plan ────────────────────────────────────────────────
    async def _prepare():
        from nicegui import run
        from api.dwarf_backup_db import DB_NAME, connect_db, close_db
        import traceback

        def _compute():
            try:
                c    = connect_db(DB_NAME)
                rows = _load_wcs_sessions(c)
                if limit:
                    rows = rows[:limit]
                close_db(c)
            except Exception as e:
                print(f'[sky_map] DB error: {e}\n{traceback.format_exc()}')
                return []

            # ── Grouper par (entry_type, entry_id) ────────────────────────────
            try:
                from collections import defaultdict
                groups = defaultdict(lambda: {'panel0': None, 'panels': []})
                for r in rows:
                    (entry_type, entry_id, panel_num, ra, dec, ps, orient, solver, solved_at,
                     obj, sdir, score, image_path, location,
                     crval1, crval2, cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2,
                     dwarf_name) = r
                    key = (entry_type, entry_id)
                    if panel_num == 0:
                        groups[key]['panel0'] = r
                    else:
                        groups[key]['panels'].append(r)
            except Exception as e:
                print(f'[sky_map] grouping error (row count={len(rows)}, cols={len(rows[0]) if rows else 0}): {e}\n{traceback.format_exc()}')
                return []

            GENERIC = {'mosaic_unknown', 'unknown', 'manual', ''}

            fps = []
            for (entry_type, entry_id), g in groups.items():
                panel0  = g['panel0']
                panels  = g['panels']   # panel_num > 0, sorted by panel_num

                # ── Choisir la row de référence pour les métadonnées ──────────
                # Mosaïque brute (panels seuls) → utiliser le panel du milieu
                # Sinon → utiliser panel0
                if panels and not panel0:
                    ref = panels[len(panels) // 2]
                else:
                    ref = panel0

                if ref is None:
                    continue

                (_, _, _, ra, dec, ps, orient, solver, solved_at,
                 obj, sdir, score, image_path, location,
                 crval1, crval2, cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2,
                 dwarf_name) = ref

                is_mosaic = '_MOSAIC_' in (sdir or '').upper()

                # ── Calculer le footprint ─────────────────────────────────────
                if panels:
                    # Mosaïque brute : bounding box réel depuis les coins des panels résolus
                    panel_rows = [(r[3], r[4], r[5], r[6]) for r in panels]
                    corners, ra_c, dec_c = _bbox_from_panel_rows(panel_rows)
                    if corners is None:
                        continue
                    # Centre réel : panel0 s'il existe (résolu sur panel du milieu)
                    # sinon centre géométrique du bbox
                    if panel0 is not None:
                        ra_c  = round(float(panel0[3]), 4)
                        dec_c = round(float(panel0[4]), 4)
                    n_panels = len(panels)
                else:
                    # Session normale ou mosaïque restichée : footprint du WCS global
                    corners = _footprint_corners(ra, dec, ps, orient)
                    if corners is None:
                        continue
                    ra_c  = round(float(ra), 4)
                    dec_c = round(float(dec), 4)
                    n_panels = 1

                label = obj if obj.lower() not in GENERIC else _strip_dwarf_prefix(sdir)

                img_url     = None
                base_folder = None
                if image_path:
                    full_path = image_path.replace('/', os.sep).replace('\\', os.sep)
                    if os.path.exists(full_path):
                        base_folder = str(os.path.dirname(location))
                        img_url     = build_preview_url(get_session_file_ref(base_folder, full_path))
                    else:
                        drive = location or ''
                        if drive:
                            full_path2 = os.path.join(drive, image_path.replace('/', os.sep))
                            if os.path.exists(full_path2):
                                base_folder = str(os.path.dirname(full_path2))
                                img_url     = build_preview_url(os.path.basename(full_path2))

                naxis1, naxis2 = _image_size_from_plate_scale(ps)

                fps.append({
                    'corners':    corners,
                    'ra':         ra_c,
                    'dec':        dec_c,
                    'label':      label[:50],
                    'solver':     solver or '?',
                    'solved_at':  solved_at[:10] if solved_at else '?',
                    'score':      int(score) if score else 0,
                    'color':      _quality_color(score),
                    'scale':      str(round(ps, 2)) if ps else '?',
                    'orientation': round(float(orient), 1) if orient is not None else 0,
                    'type':       entry_type,
                    'img_url':    img_url,
                    'base_folder': base_folder or '',
                    'is_mosaic':  is_mosaic,
                    'n_panels':   n_panels,
                    'crval1':  round(crval1, 6) if crval1 else None,
                    'crval2':  round(crval2, 6) if crval2 else None,
                    'cd1_1':   round(cd1_1, 8) if cd1_1 else None,
                    'cd1_2':   round(cd1_2, 8) if cd1_2 else None,
                    'cd2_1':   round(cd2_1, 8) if cd2_1 else None,
                    'cd2_2':   round(cd2_2, 8) if cd2_2 else None,
                    'crpix1':  round(crpix1, 2) if crpix1 else None,
                    'crpix2':  round(crpix2, 2) if crpix2 else None,
                    'naxis1':  naxis1 or 3840,
                    'naxis2':  naxis2 or 2160,
                    'dwarf_name': dwarf_name or 'Unknown',
                })

            return fps

        footprints = await run.io_bound(_compute)

        if not footprints:
            try:
                spinner.delete()
            except Exception:
                pass
            status.set_text('No footprints to display.')
            return

        ra_mean  = sum(f['ra']  for f in footprints) / len(footprints)
        dec_mean = sum(f['dec'] for f in footprints) / len(footprints)

        _register_skymap_route(footprints, ra_mean, dec_mean, server_url)

        n_astap  = sum(1 for f in footprints if f['solver'] == 'astap')
        n_nova   = sum(1 for f in footprints if f['solver'] == 'nova')
        n_local  = sum(1 for f in footprints if f['solver'] == 'local')
        n_origin = sum(1 for f in footprints if f['solver'] == 'origin')
        n_solved = len(footprints) - n_origin

        try:
            spinner.delete()
        except Exception:
            pass
        status_txt = t('sky_map_sessions_ready').format(
            n=n_solved, astap=n_astap, nova=n_nova
        )
        if n_local:
            status_txt += '  •  Local: ' + str(n_local)
        if n_origin:
            status_txt += '  •  ' + t('sky_map_mosaic_centers') + ': ' + str(n_origin)
        status.set_text(status_txt)
        open_btn.enable()

    asyncio.ensure_future(_prepare())