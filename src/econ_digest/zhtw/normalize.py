"""Character conversion, an explicit glossary, and Chinese quotation marks."""

import copy
import logging
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_SKIP_KEYS = frozenset({
    "en", "example_en", "sentence_en", "word", "phrase", "pos", "article_id", "model",
    "tier", "category", "companion_id", "cefr",
})
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]")
_QUOTES = (re.compile(r'“([^”]*)”'), re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"'))
_GLOSSARY = tuple(
    line.split("\t", 2)[:2]
    for line in Path(__file__).with_name("glossary.tsv").read_text(encoding="utf-8").splitlines()
    if line and not line.startswith("#")
)
_REPLACEMENTS = dict(_GLOSSARY)
# Preferred forms also participate so, for example, 演算法 does not become 演演算法.
_TERMS = re.compile("|".join(re.escape(term) for term in sorted(set(_REPLACEMENTS) | set(_REPLACEMENTS.values()), key=lambda term: (-len(term), term))))
_SIMPLIFIED_ONLY = frozenset(
    "们这说时为国会对发经过还进现间东车长书买卖门问题让认识语读谁调资质报纸边产业务决议选举万与专丑丛丝丢两严丧个丰临丽义乌乐乔习乡乱争亏云亚亲亿仅从仑仓仪众优伞伟传伤伦伪体侠"
    "侣侥侦侧侨俭债倾偿储兑党兰关兴养兽冈册写军农冯冻净凉减凑凤凯剂剑剥剧劝办动励劲劳势勋区医华协单卢卤卧卫厂厅历厉压厌厕厢县叁参双变叙叠叶号叹吓吗吨听启员呐呕呗呜咏咙咛响哑哗"
    "哟唤啰喷嘱团园围图圆圣场坏块坚坛坝坞坟坠垄垒垦垫墙壮声壳壶处备复够头夹夺奋奖奥妆妇妈姗娄娱婴孙学宁宝实宠审宪宫宽宾寝寻导寿将层属岁岂岗岛岭峡币帅师帐帘帜带帮帧广庄庆库应庙"
    "庞废异弃张弥弯弹归当录彻忆忧怀态总恋恳恶恼悦悬惊惧惨惩惯愤愿懒戏户扑执扩扫扬扰抚抛抢护担拟拢拣拥拦拨择挚挛挞挟挠挡挣挤挥捞损捡换据捣掳掷掸掺揽搅摄摆摇摊撑敌敛数斋斩断无旧"
    "昙昼显晋晓晕暂术机杀杂权条杨极构枪柜标栈栋栏树样栾桥桦桨桩梦检椭楼榄欢欧歼残殴毁毕毙毡气汉汤沟没沧沪泞泪泻泼泽洁洒洼浅浆浇浊测济浏浑浓涛涝涟涡涣涤润涨渍渐渔渗湾湿溃溅滚滞"
    "满滥滤滩潜潇澜濒灭灯灵灾灿炉点炼烁烂烛烟烦烧烩烫烬热焕爱爷牵犊状犹狈狞独狭狮狰狱猎猪猫献玛环玮珑琐琼电画畅疗疟疡疮疯痈痉痒痨痪瘫瘾癞皑皱盏盐监盖盗盘睁睐瞒矫矿码砖砚砾础硕"
    "碍礼祷祸禅离秃秆税稳笔简紧红线细织结给络统继维编罗职联脑脸舰艺苏药萨蓝虑虽补装见观规视觉许论设证词译诗话该误请诺课谈谢贝财负账货贪贫贬购贵贸费贼赌赔赚赞赢软轻载较辅辆输辞"
    "达运连适遗释钱铁铃铜铝银销锁锅锐键镇镜闭闯闲闷闸闹闻阅阔队阳阴阵际陆陈险随隐难雾页顶项顺顾领频颖颜风飘飞饭饮饱饺饿馆馈马骑骗鱼鸟鸡麦齐齿龙龟"
)
_warning_lock = Lock()
_warned_opencc = False


def _warn_opencc(message: str) -> None:
    global _warned_opencc
    with _warning_lock:
        if not _warned_opencc:
            logger.warning("OpenCC conversion skipped: %s", message)
            _warned_opencc = True


def _convert_text(text: str, executable: str) -> str:
    try:
        result = subprocess.run([executable, "-c", "s2tw"], input=text, capture_output=True,
                                text=True, encoding="utf-8", check=True, timeout=30)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        _warn_opencc(type(exc).__name__)
        return text
    return result.stdout


def _convert_batch(strings: list[str]) -> list[str]:
    if not strings:
        return []
    executable = shutil.which("opencc")
    if executable is None:
        _warn_opencc("opencc executable was not found")
        return list(strings)
    separator = "\nECON_DIGEST_SEPARATOR_" + uuid.uuid4().hex + "\n"
    while any(separator in text for text in strings):
        separator = "\nECON_DIGEST_SEPARATOR_" + uuid.uuid4().hex + "\n"
    converted = _convert_text(separator.join(strings), executable).split(separator)
    if len(converted) != len(strings):
        return [_convert_text(text, executable) for text in strings]
    return converted


def _finish(text: str) -> str:
    text = text.replace("臺", "台")
    text = _TERMS.sub(lambda match: _REPLACEMENTS.get(match.group(), match.group()), text)

    def quote(match: re.Match[str]) -> str:
        span = match.group(1)
        return "「" + span + "」" if _CJK.search(span) else match.group()

    for pattern in _QUOTES:
        text = pattern.sub(quote, text)
    return text


def normalize_zh_tw(text: str) -> str:
    return _finish(_convert_batch([text])[0])


def _map_strings(value: Any, transform: Callable[[str], str], skip_keys: frozenset[str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {copy.deepcopy(key): copy.deepcopy(item) if key in skip_keys else _map_strings(item, transform, skip_keys)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_map_strings(item, transform, skip_keys) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_strings(item, transform, skip_keys) for item in value)
    return copy.deepcopy(value)


def normalize_tree(value: Any, skip_keys: frozenset[str] = DEFAULT_SKIP_KEYS) -> Any:
    strings: list[str] = []

    def collect(text: str) -> str:
        strings.append(text)
        return text

    tree = _map_strings(value, collect, skip_keys)
    converted = iter(_convert_batch(strings))
    return _map_strings(tree, lambda _: _finish(next(converted)), skip_keys)


def lint_zh_tw(text: str) -> list[str]:
    remaining = {match.group() for match in _TERMS.finditer(text) if match.group() in _REPLACEMENTS}
    warnings = [f"建議將「{source}」改為「{target}」。" for source, target in _GLOSSARY if source in remaining]
    characters = sorted(set(text) & _SIMPLIFIED_ONLY)
    if characters:
        warnings.append("疑似殘留簡體字：" + "、".join(characters) + "。")
    return warnings
