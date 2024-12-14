import os, sys

if len(sys.argv) == 1: sys.argv.append('v2')
version = "v1" if sys.argv[1] == "v1" else "v2"
os.environ["version"] = version
now_dir = os.getcwd()
sys.path.insert(0, now_dir)
import warnings

warnings.filterwarnings("ignore")
import json, yaml, torch, pdb, re, shutil
import platform
import psutil
import signal
from typing import Optional
from typing import List
torch.manual_seed(233333)
tmp = os.path.join(now_dir, "TEMP")
os.makedirs(tmp, exist_ok=True)
os.environ["TEMP"] = tmp
if (os.path.exists(tmp)):
    for name in os.listdir(tmp):
        if (name == "jieba.cache"): continue
        path = "%s/%s" % (tmp, name)
        delete = os.remove if os.path.isfile(path) else shutil.rmtree
        try:
            delete(path)
        except Exception as e:
            print(str(e))
            pass
import site
import traceback
import logging
logger = logging.getLogger(__name__)
site_packages_roots = []
for path in site.getsitepackages():
    if "packages" in path:
        site_packages_roots.append(path)
if (site_packages_roots == []): site_packages_roots = ["%s/runtime/Lib/site-packages" % now_dir]
# os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1"
os.environ["all_proxy"] = ""
for site_packages_root in site_packages_roots:
    if os.path.exists(site_packages_root):
        try:
            with open("%s/users.pth" % (site_packages_root), "w") as f:
                f.write(
                    "%s\n%s/tools\n%s/tools/asr\n%s/GPT_SoVITS\n%s/tools/uvr5"
                    % (now_dir, now_dir, now_dir, now_dir, now_dir)
                )
            break
        except PermissionError as e:
            traceback.print_exc()
from tools import my_utils
import shutil
import pdb
from subprocess import Popen
from pydantic import BaseModel
import signal
from config import python_exec, infer_device, is_half, exp_root, webui_port_main, webui_port_infer_tts, webui_port_uvr5, \
    webui_port_subfix, is_share
from tools.i18n.i18n import I18nAuto, scan_language_list

language = sys.argv[-1] if sys.argv[-1] in scan_language_list() else "Auto"
os.environ["language"] = language
i18n = I18nAuto(language=language)
from scipy.io import wavfile
from tools.my_utils import load_audio, check_for_existance, check_details
from multiprocessing import cpu_count
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
# os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1' # 当遇到mps不支持的步骤时使用cpu
# try:
#     import gradio.analytics as analytics
#
#     analytics.version_check = lambda: None
# except:
#     ...
# import gradio as gr

n_cpu = cpu_count()

ngpu = torch.cuda.device_count()
gpu_infos = []
mem = []
if_gpu_ok = False

# 判断是否有能用来训练和加速推理的N卡
ok_gpu_keywords = {"10", "16", "20", "30", "40", "A2", "A3", "A4", "P4", "A50", "500", "A60", "70", "80", "90", "M4",
                   "T4", "TITAN", "L4", "4060", "H"}
set_gpu_numbers = set()
if torch.cuda.is_available() or ngpu != 0:
    for i in range(ngpu):
        gpu_name = torch.cuda.get_device_name(i)
        if any(value in gpu_name.upper() for value in ok_gpu_keywords):
            # A10#A100#V100#A40#P40#M40#K80#A4500
            if_gpu_ok = True  # 至少有一张能用的N卡
            gpu_infos.append("%s\t%s" % (i, gpu_name))
            set_gpu_numbers.add(i)
            mem.append(int(torch.cuda.get_device_properties(i).total_memory / 1024 / 1024 / 1024 + 0.4))
# # 判断是否支持mps加速
# if torch.backends.mps.is_available():
#     if_gpu_ok = True
#     gpu_infos.append("%s\t%s" % ("0", "Apple GPU"))
#     mem.append(psutil.virtual_memory().total/ 1024 / 1024 / 1024) # 实测使用系统内存作为显存不会爆显存

if if_gpu_ok and len(gpu_infos) > 0:
    gpu_info = "\n".join(gpu_infos)
    default_batch_size = min(mem) // 2
else:
    gpu_info = ("%s\t%s" % ("0", "CPU"))
    gpu_infos.append("%s\t%s" % ("0", "CPU"))
    set_gpu_numbers.add(0)
    default_batch_size = int(psutil.virtual_memory().total / 1024 / 1024 / 1024 / 2)
gpus = "-".join([i[0] for i in gpu_infos])
default_gpu_numbers = str(sorted(list(set_gpu_numbers))[0])

# FastAPI app initialization
app = FastAPI(title="gpt_sovits API")



def fix_gpu_number(input):  # 将越界的number强制改到界内
    try:
        if (int(input) not in set_gpu_numbers): return default_gpu_numbers
    except:
        return input
    return input


def fix_gpu_numbers(inputs):
    output = []
    try:
        for input in inputs.split(","): output.append(str(fix_gpu_number(input)))
        return ",".join(output)
    except:
        return inputs


pretrained_sovits_name = ["GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth",
                          "GPT_SoVITS/pretrained_models/s2G488k.pth"]
pretrained_gpt_name = [
    "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt"]

pretrained_model_list = (
pretrained_sovits_name[-int(version[-1]) + 2], pretrained_sovits_name[-int(version[-1]) + 2].replace("s2G", "s2D"),
pretrained_gpt_name[-int(version[-1]) + 2], "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
"GPT_SoVITS/pretrained_models/chinese-hubert-base")

_ = ''
for i in pretrained_model_list:
    if os.path.exists(i):
        ...
    else:
        _ += f'\n    {i}'
if _:
    print("warning:", i18n('以下模型不存在:') + _)

_ = [[], []]
for i in range(2):
    if os.path.exists(pretrained_gpt_name[i]):
        _[0].append(pretrained_gpt_name[i])
    else:
        _[0].append("")  ##没有下pretrained模型的，说不定他们是想自己从零训底模呢
    if os.path.exists(pretrained_sovits_name[i]):
        _[-1].append(pretrained_sovits_name[i])
    else:
        _[-1].append("")
pretrained_gpt_name, pretrained_sovits_name = _

SoVITS_weight_root = ["SoVITS_weights_v2", "SoVITS_weights"]
GPT_weight_root = ["GPT_weights_v2", "GPT_weights"]
for root in SoVITS_weight_root + GPT_weight_root:
    os.makedirs(root, exist_ok=True)


def get_weights_names():
    SoVITS_names = [name for name in pretrained_sovits_name if name != ""]
    for path in SoVITS_weight_root:
        for name in os.listdir(path):
            if name.endswith(".pth"): SoVITS_names.append("%s/%s" % (path, name))
    GPT_names = [name for name in pretrained_gpt_name if name != ""]
    for path in GPT_weight_root:
        for name in os.listdir(path):
            if name.endswith(".ckpt"): GPT_names.append("%s/%s" % (path, name))
    return SoVITS_names, GPT_names


SoVITS_names, GPT_names = get_weights_names()
for path in SoVITS_weight_root + GPT_weight_root:
    os.makedirs(path, exist_ok=True)


# def custom_sort_key(s):
#     # 使用正则表达式提取字符串中的数字部分和非数字部分
#     parts = re.split('(\d+)', s)
#     # 将数字部分转换为整数，非数字部分保持不变
#     parts = [int(part) if part.isdigit() else part for part in parts]
#     return parts


# def change_choices():
#     SoVITS_names, GPT_names = get_weights_names()
#     return {"choices": sorted(SoVITS_names, key=custom_sort_key), "__type__": "update"}, {
#         "choices": sorted(GPT_names, key=custom_sort_key), "__type__": "update"}


p_label = None
p_uvr5 = None
p_asr = None
p_denoise = None
p_tts_inference = None


def kill_proc_tree(pid, including_parent=True):
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        # Process already terminated
        return

    children = parent.children(recursive=True)
    for child in children:
        try:
            os.kill(child.pid, signal.SIGTERM)  # or signal.SIGKILL
        except OSError:
            pass
    if including_parent:
        try:
            os.kill(parent.pid, signal.SIGTERM)  # or signal.SIGKILL
        except OSError:
            pass


system = platform.system()


def kill_process(pid):
    if (system == "Windows"):
        cmd = "taskkill /t /f /pid %s" % pid
        os.system(cmd)
    else:
        kill_proc_tree(pid)


# def change_label(path_list):
#     global p_label
#     if (p_label == None):
#         check_for_existance([path_list])
#         path_list = my_utils.clean_path(path_list)
#         cmd = '"%s" tools/subfix_webui.py --load_list "%s" --webui_port %s --is_share %s' % (
#         python_exec, path_list, webui_port_subfix, is_share)
#         yield i18n("打标工具WebUI已开启"), {'__type__': 'update', 'visible': False}, {'__type__': 'update',
#                                                                                       'visible': True}
#         print(cmd)
#         p_label = Popen(cmd, shell=True)
#     elif (p_label != None):
#         kill_process(p_label.pid)
#         p_label = None
#         yield i18n("打标工具WebUI已关闭"), {'__type__': 'update', 'visible': True}, {'__type__': 'update',
#                                                                                      'visible': False}


# def change_uvr5():
#     global p_uvr5
#     if (p_uvr5 == None):
#         cmd = '"%s" tools/uvr5/webui.py "%s" %s %s %s' % (python_exec, infer_device, is_half, webui_port_uvr5, is_share)
#         yield i18n("UVR5已开启"), {'__type__': 'update', 'visible': False}, {'__type__': 'update', 'visible': True}
#         print(cmd)
#         p_uvr5 = Popen(cmd, shell=True)
#     elif (p_uvr5 != None):
#         kill_process(p_uvr5.pid)
#         p_uvr5 = None
#         yield i18n("UVR5已关闭"), {'__type__': 'update', 'visible': True}, {'__type__': 'update', 'visible': False}


# def change_tts_inference(bert_path, cnhubert_base_path, gpu_number, gpt_path, sovits_path, batched_infer_enabled):
#     global p_tts_inference
#     if batched_infer_enabled:
#         cmd = '"%s" GPT_SoVITS/inference_webui_fast.py "%s"' % (python_exec, language)
#     else:
#         cmd = '"%s" GPT_SoVITS/inference_webui.py "%s"' % (python_exec, language)
#     if (p_tts_inference == None):
#         os.environ["gpt_path"] = gpt_path if "/" in gpt_path else "%s/%s" % (GPT_weight_root, gpt_path)
#         os.environ["sovits_path"] = sovits_path if "/" in sovits_path else "%s/%s" % (SoVITS_weight_root, sovits_path)
#         os.environ["cnhubert_base_path"] = cnhubert_base_path
#         os.environ["bert_path"] = bert_path
#         os.environ["_CUDA_VISIBLE_DEVICES"] = fix_gpu_number(gpu_number)
#         os.environ["is_half"] = str(is_half)
#         os.environ["infer_ttswebui"] = str(webui_port_infer_tts)
#         os.environ["is_share"] = str(is_share)
#         yield i18n("TTS推理进程已开启"), {'__type__': 'update', 'visible': False}, {'__type__': 'update',
#                                                                                     'visible': True}
#         print(cmd)
#         p_tts_inference = Popen(cmd, shell=True)
#     elif (p_tts_inference != None):
#         kill_process(p_tts_inference.pid)
#         p_tts_inference = None
#         yield i18n("TTS推理进程已关闭"), {'__type__': 'update', 'visible': True}, {'__type__': 'update',
#                                                                                    'visible': False}






from tools.asr.config import asr_dict


def open_asr(asr_inp_dir, asr_opt_dir, asr_model, asr_model_size, asr_lang, asr_precision):
    global p_asr
    if (p_asr == None):
        asr_inp_dir = my_utils.clean_path(asr_inp_dir)
        asr_opt_dir = my_utils.clean_path(asr_opt_dir)
        check_for_existance([asr_inp_dir])
        cmd = f'"{python_exec}" tools/asr/{asr_dict[asr_model]["path"]}'
        cmd += f' -i "{asr_inp_dir}"'
        cmd += f' -o "{asr_opt_dir}"'
        cmd += f' -s {asr_model_size}'
        cmd += f' -l {asr_lang}'
        cmd += f" -p {asr_precision}"
        output_file_name = os.path.basename(asr_inp_dir)
        output_folder = asr_opt_dir or "output/asr_opt"
        output_file_path = os.path.abspath(f'{output_folder}/{output_file_name}.list')
        yield "ASR任务开启：%s" % cmd, {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                 "visible": True}, {
            "__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}
        print(cmd)
        p_asr = Popen(cmd, shell=True)
        p_asr.wait()
        p_asr = None
        yield f"ASR任务完成, 查看终端进行下一步", {"__type__": "update", "visible": True}, {"__type__": "update",
                                                                                            "visible": False}, {
            "__type__": "update", "value": output_file_path}, {"__type__": "update", "value": output_file_path}, {
            "__type__": "update", "value": asr_inp_dir}
    else:
        yield "已有正在进行的ASR任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}, {"__type__": "update"}, {"__type__": "update"}, {
            "__type__": "update"}
        # return None


def close_asr():
    global p_asr
    if (p_asr != None):
        kill_process(p_asr.pid)
        p_asr = None
    return "已终止ASR进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


def open_denoise(denoise_inp_dir, denoise_opt_dir):
    global p_denoise
    if (p_denoise == None):
        denoise_inp_dir = my_utils.clean_path(denoise_inp_dir)
        denoise_opt_dir = my_utils.clean_path(denoise_opt_dir)
        check_for_existance([denoise_inp_dir])
        cmd = '"%s" tools/cmd-denoise.py -i "%s" -o "%s" -p %s' % (
        python_exec, denoise_inp_dir, denoise_opt_dir, "float16" if is_half == True else "float32")

        yield "语音降噪任务开启：%s" % cmd, {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                      "visible": True}, {
            "__type__": "update"}, {"__type__": "update"}
        print(cmd)
        p_denoise = Popen(cmd, shell=True)
        p_denoise.wait()
        p_denoise = None
        yield f"语音降噪任务完成, 查看终端进行下一步", {"__type__": "update", "visible": True}, {"__type__": "update",
                                                                                                 "visible": False}, {
            "__type__": "update", "value": denoise_opt_dir}, {"__type__": "update", "value": denoise_opt_dir}
    else:
        yield "已有正在进行的语音降噪任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}, {"__type__": "update"}, {"__type__": "update"}
        # return None


def close_denoise():
    global p_denoise
    if (p_denoise != None):
        kill_process(p_denoise.pid)
        p_denoise = None
    return "已终止语音降噪进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


p_train_SoVITS = None


def open1Ba(batch_size, total_epoch, exp_name, text_low_lr_rate, if_save_latest, if_save_every_weights,
            save_every_epoch, gpu_numbers1Ba, pretrained_s2G, pretrained_s2D):
    global p_train_SoVITS
    if (p_train_SoVITS == None):
        with open("GPT_SoVITS/configs/s2.json") as f:
            data = f.read()
            data = json.loads(data)
        s2_dir = "%s/%s" % (exp_root, exp_name)
        os.makedirs("%s/logs_s2" % (s2_dir), exist_ok=True)
        if check_for_existance([s2_dir], is_train=True):
            check_details([s2_dir], is_train=True)
        if (is_half == False):
            data["train"]["fp16_run"] = False
            batch_size = max(1, batch_size // 2)
        data["train"]["batch_size"] = batch_size
        data["train"]["epochs"] = total_epoch
        data["train"]["text_low_lr_rate"] = text_low_lr_rate
        data["train"]["pretrained_s2G"] = pretrained_s2G
        data["train"]["pretrained_s2D"] = pretrained_s2D
        data["train"]["if_save_latest"] = if_save_latest
        data["train"]["if_save_every_weights"] = if_save_every_weights
        data["train"]["save_every_epoch"] = save_every_epoch
        data["train"]["gpu_numbers"] = gpu_numbers1Ba
        data["model"]["version"] = version
        data["data"]["exp_dir"] = data["s2_ckpt_dir"] = s2_dir
        data["save_weight_dir"] = SoVITS_weight_root[-int(version[-1]) + 2]
        data["name"] = exp_name
        data["version"] = version
        tmp_config_path = "%s/tmp_s2.json" % tmp
        with open(tmp_config_path, "w") as f:
            f.write(json.dumps(data))

        cmd = '"%s" GPT_SoVITS/s2_train.py --config "%s"' % (python_exec, tmp_config_path)
        yield "SoVITS训练开始：%s" % cmd, {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                    "visible": True}
        print(cmd)
        p_train_SoVITS = Popen(cmd, shell=True)
        p_train_SoVITS.wait()
        p_train_SoVITS = None
        yield "SoVITS训练完成", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的SoVITS训练任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1Ba():
    global p_train_SoVITS
    if (p_train_SoVITS != None):
        kill_process(p_train_SoVITS.pid)
        p_train_SoVITS = None
    return "已终止SoVITS训练", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


p_train_GPT = None


def open1Bb(batch_size, total_epoch, exp_name, if_dpo, if_save_latest, if_save_every_weights, save_every_epoch,
            gpu_numbers, pretrained_s1):
    global p_train_GPT
    if (p_train_GPT == None):
        with open(
                "GPT_SoVITS/configs/s1longer.yaml" if version == "v1" else "GPT_SoVITS/configs/s1longer-v2.yaml") as f:
            data = f.read()
            data = yaml.load(data, Loader=yaml.FullLoader)
        s1_dir = "%s/%s" % (exp_root, exp_name)
        os.makedirs("%s/logs_s1" % (s1_dir), exist_ok=True)
        if check_for_existance([s1_dir], is_train=True):
            check_details([s1_dir], is_train=True)
        if (is_half == False):
            data["train"]["precision"] = "32"
            batch_size = max(1, batch_size // 2)
        data["train"]["batch_size"] = batch_size
        data["train"]["epochs"] = total_epoch
        data["pretrained_s1"] = pretrained_s1
        data["train"]["save_every_n_epoch"] = save_every_epoch
        data["train"]["if_save_every_weights"] = if_save_every_weights
        data["train"]["if_save_latest"] = if_save_latest
        data["train"]["if_dpo"] = if_dpo
        data["train"]["half_weights_save_dir"] = GPT_weight_root[-int(version[-1]) + 2]
        data["train"]["exp_name"] = exp_name
        data["train_semantic_path"] = "%s/6-name2semantic.tsv" % s1_dir
        data["train_phoneme_path"] = "%s/2-name2text.txt" % s1_dir
        data["output_dir"] = "%s/logs_s1" % s1_dir
        # data["version"]=version

        os.environ["_CUDA_VISIBLE_DEVICES"] = fix_gpu_numbers(gpu_numbers.replace("-", ","))
        os.environ["hz"] = "25hz"
        tmp_config_path = "%s/tmp_s1.yaml" % tmp
        with open(tmp_config_path, "w") as f:
            f.write(yaml.dump(data, default_flow_style=False))
        # cmd = '"%s" GPT_SoVITS/s1_train.py --config_file "%s" --train_semantic_path "%s/6-name2semantic.tsv" --train_phoneme_path "%s/2-name2text.txt" --output_dir "%s/logs_s1"'%(python_exec,tmp_config_path,s1_dir,s1_dir,s1_dir)
        cmd = '"%s" GPT_SoVITS/s1_train.py --config_file "%s" ' % (python_exec, tmp_config_path)
        yield "GPT训练开始：%s" % cmd, {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
        print(cmd)
        p_train_GPT = Popen(cmd, shell=True)
        p_train_GPT.wait()
        p_train_GPT = None
        yield "GPT训练完成", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的GPT训练任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1Bb():
    global p_train_GPT
    if (p_train_GPT != None):
        kill_process(p_train_GPT.pid)
        p_train_GPT = None
    return "已终止GPT训练", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


ps_slice = []


def open_slice(inp, opt_root, threshold, min_length, min_interval, hop_size, max_sil_kept, _max, alpha, n_parts):
    global ps_slice
    inp = my_utils.clean_path(inp)
    opt_root = my_utils.clean_path(opt_root)
    check_for_existance([inp])
    if (os.path.exists(inp) == False):
        yield "输入路径不存在", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}, {
            "__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}
        return
    if os.path.isfile(inp):
        n_parts = 1
    elif os.path.isdir(inp):
        pass
    else:
        yield "输入路径存在但既不是文件也不是文件夹", {"__type__": "update", "visible": True}, {"__type__": "update",
                                                                                                "visible": False}, {
            "__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}
        return
    if (ps_slice == []):
        for i_part in range(n_parts):
            cmd = '"%s" tools/slice_audio.py "%s" "%s" %s %s %s %s %s %s %s %s %s''' % (
            python_exec, inp, opt_root, threshold, min_length, min_interval, hop_size, max_sil_kept, _max, alpha,
            i_part, n_parts)
            print(cmd)
            p = Popen(cmd, shell=True)
            ps_slice.append(p)
        yield "切割执行中", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}, {
            "__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}
        for p in ps_slice:
            p.wait()
        ps_slice = []
        yield "切割结束", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}, {
            "__type__": "update", "value": opt_root}, {"__type__": "update", "value": opt_root}, {"__type__": "update",
                                                                                                  "value": opt_root}
    else:
        yield "已有正在进行的切割任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}, {"__type__": "update"}, {"__type__": "update"}, {
            "__type__": "update"}


def close_slice():
    global ps_slice
    if (ps_slice != []):
        for p_slice in ps_slice:
            try:
                kill_process(p_slice.pid)
            except:
                traceback.print_exc()
        ps_slice = []
    return "已终止所有切割进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


ps1a = []


def open1a(inp_text, inp_wav_dir, exp_name, gpu_numbers, bert_pretrained_dir):
    global ps1a
    inp_text = my_utils.clean_path(inp_text)
    inp_wav_dir = my_utils.clean_path(inp_wav_dir)
    if check_for_existance([inp_text, inp_wav_dir], is_dataset_processing=True):
        check_details([inp_text, inp_wav_dir], is_dataset_processing=True)
    if (ps1a == []):
        opt_dir = "%s/%s" % (exp_root, exp_name)
        config = {
            "inp_text": inp_text,
            "inp_wav_dir": inp_wav_dir,
            "exp_name": exp_name,
            "opt_dir": opt_dir,
            "bert_pretrained_dir": bert_pretrained_dir,
        }
        gpu_names = gpu_numbers.split("-")
        all_parts = len(gpu_names)
        for i_part in range(all_parts):
            config.update(
                {
                    "i_part": str(i_part),
                    "all_parts": str(all_parts),
                    "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                    "is_half": str(is_half)
                }
            )
            os.environ.update(config)
            cmd = '"%s" GPT_SoVITS/prepare_datasets/1-get-text.py' % python_exec
            print(cmd)
            p = Popen(cmd, shell=True)
            ps1a.append(p)
        yield "文本进程执行中", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
        for p in ps1a:
            p.wait()
        opt = []
        for i_part in range(all_parts):
            txt_path = "%s/2-name2text-%s.txt" % (opt_dir, i_part)
            with open(txt_path, "r", encoding="utf8") as f:
                opt += f.read().strip("\n").split("\n")
            os.remove(txt_path)
        path_text = "%s/2-name2text.txt" % opt_dir
        with open(path_text, "w", encoding="utf8") as f:
            f.write("\n".join(opt) + "\n")
        ps1a = []
        if len("".join(opt)) > 0:
            yield "文本进程成功", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
        else:
            yield "文本进程失败", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的文本任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1a():
    global ps1a
    if (ps1a != []):
        for p1a in ps1a:
            try:
                kill_process(p1a.pid)
            except:
                traceback.print_exc()
        ps1a = []
    return "已终止所有1a进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


ps1b = []


def open1b(inp_text, inp_wav_dir, exp_name, gpu_numbers, ssl_pretrained_dir):
    global ps1b
    inp_text = my_utils.clean_path(inp_text)
    inp_wav_dir = my_utils.clean_path(inp_wav_dir)
    if check_for_existance([inp_text, inp_wav_dir], is_dataset_processing=True):
        check_details([inp_text, inp_wav_dir], is_dataset_processing=True)
    if (ps1b == []):
        config = {
            "inp_text": inp_text,
            "inp_wav_dir": inp_wav_dir,
            "exp_name": exp_name,
            "opt_dir": "%s/%s" % (exp_root, exp_name),
            "cnhubert_base_dir": ssl_pretrained_dir,
            "is_half": str(is_half)
        }
        gpu_names = gpu_numbers.split("-")
        all_parts = len(gpu_names)
        for i_part in range(all_parts):
            config.update(
                {
                    "i_part": str(i_part),
                    "all_parts": str(all_parts),
                    "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                }
            )
            os.environ.update(config)
            cmd = '"%s" GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py' % python_exec
            print(cmd)
            p = Popen(cmd, shell=True)
            ps1b.append(p)
        yield "SSL提取进程执行中", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
        for p in ps1b:
            p.wait()
        ps1b = []
        yield "SSL提取进程结束", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的SSL提取任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1b():
    global ps1b
    if (ps1b != []):
        for p1b in ps1b:
            try:
                kill_process(p1b.pid)
            except:
                traceback.print_exc()
        ps1b = []
    return "已终止所有1b进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


ps1c = []


def open1c(inp_text, exp_name, gpu_numbers, pretrained_s2G_path):
    global ps1c
    inp_text = my_utils.clean_path(inp_text)
    if check_for_existance([inp_text, ''], is_dataset_processing=True):
        check_details([inp_text, ''], is_dataset_processing=True)
    if (ps1c == []):
        opt_dir = "%s/%s" % (exp_root, exp_name)
        config = {
            "inp_text": inp_text,
            "exp_name": exp_name,
            "opt_dir": opt_dir,
            "pretrained_s2G": pretrained_s2G_path,
            "s2config_path": "GPT_SoVITS/configs/s2.json",
            "is_half": str(is_half)
        }
        gpu_names = gpu_numbers.split("-")
        all_parts = len(gpu_names)
        for i_part in range(all_parts):
            config.update(
                {
                    "i_part": str(i_part),
                    "all_parts": str(all_parts),
                    "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                }
            )
            os.environ.update(config)
            cmd = '"%s" GPT_SoVITS/prepare_datasets/3-get-semantic.py' % python_exec
            print(cmd)
            p = Popen(cmd, shell=True)
            ps1c.append(p)
        yield "语义token提取进程执行中", {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                    "visible": True}
        for p in ps1c:
            p.wait()
        opt = ["item_name\tsemantic_audio"]
        path_semantic = "%s/6-name2semantic.tsv" % opt_dir
        for i_part in range(all_parts):
            semantic_path = "%s/6-name2semantic-%s.tsv" % (opt_dir, i_part)
            with open(semantic_path, "r", encoding="utf8") as f:
                opt += f.read().strip("\n").split("\n")
            os.remove(semantic_path)
        with open(path_semantic, "w", encoding="utf8") as f:
            f.write("\n".join(opt) + "\n")
        ps1c = []
        yield "语义token提取进程结束", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的语义token提取任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1c():
    global ps1c
    if (ps1c != []):
        for p1c in ps1c:
            try:
                kill_process(p1c.pid)
            except:
                traceback.print_exc()
        ps1c = []
    return "已终止所有语义token进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


#####inp_text,inp_wav_dir,exp_name,gpu_numbers1a,gpu_numbers1Ba,gpu_numbers1c,bert_pretrained_dir,cnhubert_base_dir,pretrained_s2G
ps1abc = []


def open1abc(inp_text, inp_wav_dir, exp_name, gpu_numbers1a, gpu_numbers1Ba, gpu_numbers1c, bert_pretrained_dir,
             ssl_pretrained_dir, pretrained_s2G_path):
    global ps1abc
    inp_text = my_utils.clean_path(inp_text)
    inp_wav_dir = my_utils.clean_path(inp_wav_dir)
    if check_for_existance([inp_text, inp_wav_dir], is_dataset_processing=True):
        check_details([inp_text, inp_wav_dir], is_dataset_processing=True)
    if (ps1abc == []):
        opt_dir = "%s/%s" % (exp_root, exp_name)
        try:
            #############################1a
            path_text = "%s/2-name2text.txt" % opt_dir
            if (os.path.exists(path_text) == False or (os.path.exists(path_text) == True and len(
                    open(path_text, "r", encoding="utf8").read().strip("\n").split("\n")) < 2)):
                config = {
                    "inp_text": inp_text,
                    "inp_wav_dir": inp_wav_dir,
                    "exp_name": exp_name,
                    "opt_dir": opt_dir,
                    "bert_pretrained_dir": bert_pretrained_dir,
                    "is_half": str(is_half)
                }
                gpu_names = gpu_numbers1a.split("-")
                all_parts = len(gpu_names)
                for i_part in range(all_parts):
                    config.update(
                        {
                            "i_part": str(i_part),
                            "all_parts": str(all_parts),
                            "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                        }
                    )
                    os.environ.update(config)
                    cmd = '"%s" GPT_SoVITS/prepare_datasets/1-get-text.py' % python_exec
                    print(cmd)
                    p = Popen(cmd, shell=True)
                    ps1abc.append(p)
                yield "进度：1a-ing", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
                for p in ps1abc: p.wait()

                opt = []
                for i_part in range(all_parts):  # txt_path="%s/2-name2text-%s.txt"%(opt_dir,i_part)
                    txt_path = "%s/2-name2text-%s.txt" % (opt_dir, i_part)
                    with open(txt_path, "r", encoding="utf8") as f:
                        opt += f.read().strip("\n").split("\n")
                    os.remove(txt_path)
                with open(path_text, "w", encoding="utf8") as f:
                    f.write("\n".join(opt) + "\n")
                assert len("".join(opt)) > 0, "1Aa-文本获取进程失败"
            yield "进度：1a-done", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
            ps1abc = []
            #############################1b
            config = {
                "inp_text": inp_text,
                "inp_wav_dir": inp_wav_dir,
                "exp_name": exp_name,
                "opt_dir": opt_dir,
                "cnhubert_base_dir": ssl_pretrained_dir,
            }
            gpu_names = gpu_numbers1Ba.split("-")
            all_parts = len(gpu_names)
            for i_part in range(all_parts):
                config.update(
                    {
                        "i_part": str(i_part),
                        "all_parts": str(all_parts),
                        "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                    }
                )
                os.environ.update(config)
                cmd = '"%s" GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py' % python_exec
                print(cmd)
                p = Popen(cmd, shell=True)
                ps1abc.append(p)
            yield "进度：1a-done, 1b-ing", {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                     "visible": True}
            for p in ps1abc: p.wait()
            yield "进度：1a1b-done", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
            ps1abc = []
            #############################1c
            path_semantic = "%s/6-name2semantic.tsv" % opt_dir
            if (os.path.exists(path_semantic) == False or (
                    os.path.exists(path_semantic) == True and os.path.getsize(path_semantic) < 31)):
                config = {
                    "inp_text": inp_text,
                    "exp_name": exp_name,
                    "opt_dir": opt_dir,
                    "pretrained_s2G": pretrained_s2G_path,
                    "s2config_path": "GPT_SoVITS/configs/s2.json",
                }
                gpu_names = gpu_numbers1c.split("-")
                all_parts = len(gpu_names)
                for i_part in range(all_parts):
                    config.update(
                        {
                            "i_part": str(i_part),
                            "all_parts": str(all_parts),
                            "_CUDA_VISIBLE_DEVICES": fix_gpu_number(gpu_names[i_part]),
                        }
                    )
                    os.environ.update(config)
                    cmd = '"%s" GPT_SoVITS/prepare_datasets/3-get-semantic.py' % python_exec
                    print(cmd)
                    p = Popen(cmd, shell=True)
                    ps1abc.append(p)
                yield "进度：1a1b-done, 1cing", {"__type__": "update", "visible": False}, {"__type__": "update",
                                                                                          "visible": True}
                for p in ps1abc: p.wait()

                opt = ["item_name\tsemantic_audio"]
                for i_part in range(all_parts):
                    semantic_path = "%s/6-name2semantic-%s.tsv" % (opt_dir, i_part)
                    with open(semantic_path, "r", encoding="utf8") as f:
                        opt += f.read().strip("\n").split("\n")
                    os.remove(semantic_path)
                with open(path_semantic, "w", encoding="utf8") as f:
                    f.write("\n".join(opt) + "\n")
                yield "进度：all-done", {"__type__": "update", "visible": False}, {"__type__": "update", "visible": True}
            ps1abc = []
            yield "一键三连进程结束", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
        except:
            traceback.print_exc()
            close1abc()
            yield "一键三连中途报错", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}
    else:
        yield "已有正在进行的一键三连任务，需先终止才能开启下一次任务", {"__type__": "update", "visible": False}, {
            "__type__": "update", "visible": True}


def close1abc():
    global ps1abc
    if (ps1abc != []):
        for p1abc in ps1abc:
            try:
                kill_process(p1abc.pid)
            except:
                traceback.print_exc()
        ps1abc = []
    return "已终止所有一键三连进程", {"__type__": "update", "visible": True}, {"__type__": "update", "visible": False}


def switch_version(version_):
    os.environ['version'] = version_
    global version
    version = version_
    if pretrained_sovits_name[-int(version[-1]) + 2] != '' and pretrained_gpt_name[-int(version[-1]) + 2] != '':
        ...
    else:
        # gr.Warning(i18n(f'未下载{version.upper()}模型'))
        ...
    return {'__type__': 'update', 'value': pretrained_sovits_name[-int(version[-1]) + 2]}, {'__type__': 'update',
                                                                                            'value':
                                                                                                pretrained_sovits_name[
                                                                                                    -int(version[
                                                                                                             -1]) + 2].replace(
                                                                                                    "s2G", "s2D")}, {
        '__type__': 'update', 'value': pretrained_gpt_name[-int(version[-1]) + 2]}, {'__type__': 'update',
                                                                                     'value': pretrained_gpt_name[
                                                                                         -int(version[-1]) + 2]}, {
        '__type__': 'update', 'value': pretrained_sovits_name[-int(version[-1]) + 2]}


if os.path.exists('GPT_SoVITS/text/G2PWModel'):
    ...
else:
    cmd = '"%s" GPT_SoVITS/download.py' % python_exec
    p = Popen(cmd, shell=True)
    p.wait()


def sync(text):
    return {'__type__': 'update', 'value': text}

class sliceRequest(BaseModel):
     inp: str
     opt_root: str
     threshold: Optional[int] = -34
     min_length: Optional[int] = 4000
     min_interval: Optional[int] = 300
     hop_size: Optional[int] = 10
     max_sil_kept: Optional[int] = 500
     _max: Optional[float] = 0.9
     alpha: Optional[float] = 0.25
     n_parts: Optional[int] = 4

@app.post("/gpt_sovits/open_slice")
async def open_slice_api(request: sliceRequest):
    try:
        print(request)
        open_slice(
            request.inp,
            request.opt_root,
            request.threshold,
            request.min_length,
            request.min_interval,
            request.hop_size,
            request.max_sil_kept,
            request._max,
            request.alpha,
            request.n_parts
        )
        return {"status": "success", "message": "成功进行音频切割"}
    except:
        logger.error(f"进行音频切割时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

class denoiseRequest(BaseModel):
    denoise_inp_dir: str
    denoise_opt_dir: str

@app.post("/gpt_sovits/open_denoise")
async def open_denoise_api(reqeust: denoiseRequest):
    try:
        open_denoise(
            reqeust.denoise_inp_dir,
            reqeust.denoise_opt_dir
        )
        return {"status": "success", "message": "成功进行音频降噪"}
    except:
        logger.error(f"进行音频降噪时异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

class asrRequest(BaseModel):
    asr_inp_dir: str
    asr_opt_dir: str
    asr_model: Optional[str] = "达摩 ASR (中文)"
    asr_model_size: Optional[str] = "large"
    asr_lang: Optional[str]= "zh"
    asr_precision: Optional[str]= "float32"

@app.post("/gpt_sovits/open_asr")
async def open_asr_api(request: asrRequest):
   try:
     open_asr(
         request.asr_inp_dir,
         request.asr_opt_dir,
         request.asr_model,
         request.asr_model_size,
         request.asr_lang,
         request.asr_precision
     )
     return {"status": "success", "message": "成功进行ASR"}
   except:
     logger.error(f"进行ASR时出错: {str(e)}")
     raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

class abcRequest(BaseModel):
    inp_text: str
    inp_wav_dir: str
    exp_name: str
    gpu_numbers1a: Optional[str] = "0-0"
    gpu_numbers1Ba: Optional[str] = "0-0"
    gpu_numbers1c: Optional[str] = "0-0"
    bert_pretrained_dir: Optional[str]= "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
    ssl_pretrained_dir: Optional[str]= "GPT_SoVITS/pretrained_models/chinese-hubert-base"
    pretrained_s2G_path: Optional[str]= "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"

@app.post("/gpt_sovits/open1abc")
async def open_1abc_api(request: abcRequest):
    try:
       open1abc(
           request.inp_text,
           request.inp_wav_dir,
           request.exp_name,
           request.gpu_numbers1a,
           request.gpu_numbers1Ba,
           request.gpu_numbers1c,
           request.bert_pretrained_dir,
           request.ssl_pretrained_dir,
           request.pretrained_s2G_path
       )
    except:
        logger.error(f"进行一键三连时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class sovitsTrainRequest(BaseModel):
    exp_name: str
    if_save_latest: Optional[bool] = True
    if_save_every_weights: Optional[bool] = True
    batch_size: Optional[int] = 3
    total_epoch: Optional[int] = 8
    text_low_lr_rate: Optional[float] = 0.4
    save_every_epoch: Optional[int] = 4
    gpu_numbers1Ba: Optional[str]= "0"
    pretrained_s2G: Optional[str]="GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"
    pretrained_s2D: Optional[str]="GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2D2333k.pth"
@app.post("/gpt_sovits/sovits_train")
async def sovits_train_api(request: sovitsTrainRequest):
    try:
         open1Ba(
             request.batch_size,
             request.total_epoch,
             request.exp_name,
             request.text_low_lr_rate,
             request.if_save_latest,
             request.if_save_every_weights,
             request.save_every_epoch,
             request.gpu_numbers1Ba,
             request.pretrained_s2G,
             request.pretrained_s2D
         )
    except:
        logger.error(f"进行sovits训练时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class gptTrainRequest(BaseModel):
    exp_name: str
    batch_size: Optional[int] = 3
    total_epoch: Optional[int] = 15
    if_dpo: Optional[bool] = True
    if_save_latest: Optional[bool] = True
    if_save_every_weights: Optional[bool] = True
    save_every_epoch: Optional[int] = 5
    gpu_numbers: Optional[str] = "0"
    pretrained_s1: Optional[str] = "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
@app.post("/gpt_sovits/gpt_train")
async def gpt_train_api(request: gptTrainRequest):
     try:
        open1Bb(
            request.batch_size,
            request.total_epoch,
            request.exp_name,
            request.if_dpo,
            request.if_save_latest,
            request.if_save_every_weights,
            request.save_every_epoch,
            request.gpu_numbers,
            request.pretrained_s1
        )
     except:
        logger.error(f"进行gpt训练时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

if __name__ == "__main__":
    print("start server...")
    print("gpt_sovits api 服务开启了")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0",port=9878)