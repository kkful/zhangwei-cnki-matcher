"""滑块验证码自动破解 - ddddocr + OpenCV 双引擎"""
import json, time, base64, random, urllib.request
import numpy as np

DDDDOCR = None
try:
    import ddddocr
    DDDDOCR = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
except Exception:
    pass

PROXY = "http://localhost:3456"

def get(path):
    with urllib.request.urlopen(PROXY + path, timeout=15) as r:
        return json.loads(r.read())

def eval_js(tab, js):
    req = urllib.request.Request(f'{PROXY}/eval?target={tab}', data=js.encode())
    req.add_header('Content-Type', 'text/plain')
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode('utf-8', errors='replace')
    try:
        wrapped = json.loads(raw)
        if isinstance(wrapped, dict) and 'value' in wrapped:
            return wrapped['value']
    except:
        pass
    return raw


def find_gap_tencent(tab):
    """腾讯天御验证码：ddddocr优先，OpenCV兜底"""
    info_str = eval_js(tab, """(function(){
        var r = {};
        var bgs = document.querySelectorAll('.tencent-captcha-dy__bg-placeholder');
        for(var i=0;i<bgs.length;i++){
            if(bgs[i].naturalWidth>50){
                r.bg = bgs[i].src;
                r.bgNaturalW = bgs[i].naturalWidth;
                r.bgDisplayW = bgs[i].getBoundingClientRect().width;
                break;
            }
        }
        var sliderImg = document.querySelector('.tencent-captcha-dy__slider-img--normal');
        if(!sliderImg) sliderImg = document.querySelector('.tencent-captcha-dy__slider-img--active');
        if(sliderImg) r.blockImg = sliderImg.src;
        var block = document.querySelector('.tencent-captcha-dy__slider-block');
        if(block){
            var rect = block.getBoundingClientRect();
            r.blockX = rect.x; r.blockY = rect.y;
            r.blockW = rect.width; r.blockH = rect.height;
            r.blockLeft = block.style.left || '';
        }
        r.found = !!(r.bg && block);
        return JSON.stringify(r);
    })()""")
    info = json.loads(info_str)
    if not info.get('found') or not info.get('bg'):
        return None

    def b64_to_bytes(b64):
        if ',' in b64: b64 = b64.split(',')[1]
        return base64.b64decode(b64)

    bg_bytes = b64_to_bytes(info['bg'])

    gap_x = None
    if DDDDOCR and info.get('blockImg'):
        try:
            block_bytes = b64_to_bytes(info['blockImg'])
            res = DDDDOCR.slide_match(block_bytes, bg_bytes, simple_target=True)
            gap_x = res.get('target', [0])[0]
        except Exception:
            pass

    if gap_x is None:
        try:
            import cv2
            bg_arr = np.frombuffer(bg_bytes, np.uint8)
            bg = cv2.imdecode(bg_arr, cv2.IMREAD_COLOR)
            if bg is not None:
                gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                h, w = edges.shape
                right = edges[:, int(w*0.3):int(w*0.9)]
                col_sums = np.sum(right, axis=0)
                if len(col_sums) > 0:
                    gap_x = int(w * 0.3) + int(np.argmax(col_sums))
        except Exception:
            pass

    if gap_x is None:
        return None

    natural_w = info.get('bgNaturalW', 300)
    display_w = info.get('bgDisplayW', 300)
    scale = display_w / natural_w if natural_w > 0 else 1.0
    gap_display = int(gap_x * scale)

    block_left_str = info.get('blockLeft', '0px').replace('px', '')
    try:
        block_offset = float(block_left_str)
    except:
        block_offset = 0

    return {
        'sx': int(info['blockX'] + info['blockW'] / 2),
        'sy': int(info['blockY'] + info['blockH'] / 2),
        'distance': gap_display - int(block_offset)
    }


def find_gap_geetest(tab):
    """极验验证码：从 canvas 找缺口"""
    import cv2
    info_str = eval_js(tab, """(function(){
        var r = {};
        var bg = document.querySelector('.geetest_canvas_bg canvas');
        if(bg) r.bg = bg.toDataURL('image/png');
        var btn = document.querySelector('.geetest_slider_button');
        if(btn) {
            var rect = btn.getBoundingClientRect();
            r.sx = rect.x + rect.width/2;
            r.sy = rect.y + rect.height/2;
        }
        r.found = !!(bg && btn);
        return JSON.stringify(r);
    })()""")
    info = json.loads(info_str)
    if not info.get('found') or not info.get('bg'):
        return None

    def b64_to_cv(b64):
        if ',' in b64: b64 = b64.split(',')[1]
        arr = np.frombuffer(base64.b64decode(b64), np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    bg = b64_to_cv(info['bg'])
    gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    h, w = edges.shape
    right = edges[:, int(w*0.4):int(w*0.9)]
    col_sums = np.sum(right, axis=0)
    gap_x = int(w * 0.4) + int(np.argmax(col_sums))

    cw = bg.shape[1]
    rw = float(eval_js(tab, "var c=document.querySelector('.geetest_canvas_bg canvas');return c?c.getBoundingClientRect().width:1;"))
    scale = rw / cw if cw > 0 else 1.0

    return {
        'sx': int(info.get('sx', 0)),
        'sy': int(info.get('sy', 0)),
        'distance': int(gap_x * scale)
    }


def drag_via_mouseevent(tab, sx, sy, distance):
    """通过 JS MouseEvent 模拟拖拽"""
    if distance <= 0:
        return False

    track = []
    cur, mid = 0, int(distance * 0.65)
    while cur < distance:
        if cur < distance * 0.25:
            cur += random.randint(4, 14)
        elif cur < mid:
            cur += random.randint(3, 9)
        elif distance - cur < 8:
            cur += random.randint(1, 3)
        else:
            cur += random.randint(2, 5)
        if cur > distance:
            cur = distance
        track.append(cur)
    if not track or track[-1] != distance:
        track.append(distance)

    eval_js(tab, f"""(function(){{
var b=document.querySelector('.tencent-captcha-dy__slider-block');
if(!b)b=document.querySelector('.geetest_slider_button');
if(!b)return;
b.setAttribute('data-sv','1');
b.dispatchEvent(new MouseEvent('mousedown',{{clientX:{sx},clientY:{sy},bubbles:true,cancelable:true,view:window}}));
}})()""")
    time.sleep(random.uniform(0.03, 0.08))

    for step in track:
        x = sx + step
        y = sy + random.randint(-3, 3)
        eval_js(tab, f"""(function(){{
var b=document.querySelector('[data-sv]');if(!b)return;
var e=new MouseEvent('mousemove',{{clientX:{x},clientY:{y},bubbles:true,cancelable:true,view:window}});
document.dispatchEvent(e);
}})()""")
        time.sleep(random.uniform(0.004, 0.015))

    time.sleep(random.uniform(0.04, 0.1))
    eval_js(tab, f"""(function(){{
var b=document.querySelector('[data-sv]');if(!b)return;
var e=new MouseEvent('mouseup',{{clientX:{sx+distance},clientY:{sy},bubbles:true,cancelable:true,view:window}});
b.dispatchEvent(e);
}})()""")
    return True


def solve_slider(tab, max_attempts=3):
    """主入口：检测并解决滑块验证码"""
    for attempt in range(max_attempts):
        cap_type = eval_js(tab, """(function(){
            if(document.querySelector('#tCaptchaDyMainWrap')) return 'tencent';
            if(document.querySelector('.geetest_canvas_bg canvas')) return 'geetest';
            return 'none';
        })()""")

        if cap_type == 'none' or 'none' in str(cap_type):
            return False

        if 'tencent' in str(cap_type):
            result = find_gap_tencent(tab)
        else:
            result = find_gap_geetest(tab)

        if not result or result['distance'] <= 0:
            time.sleep(1)
            continue

        drag_via_mouseevent(tab, result['sx'], result['sy'], result['distance'])
        time.sleep(2)

        still = eval_js(tab, """(function(){
            if(document.querySelector('#tCaptchaDyMainWrap')) return 'yes';
            if(document.querySelector('.geetest_panel')) return 'yes';
            return 'no';
        })()""")
        if still == 'no' or 'no' in str(still):
            return True

        time.sleep(1)

    return False
