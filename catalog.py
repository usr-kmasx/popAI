"""Single source of profile defaults and output presets for API and UI."""
import math

RESOLUTIONS = {'720p': (1280,720), '900p': (1600,900), '1080p': (1920,1080),
               '1440p': (2560,1440), '1800p': (3200,1800), '2160p': (3840,2160)}
ASPECT_RATIOS = {'16:9':(16,9), '9:16':(9,16), '9:20':(9,20),
                 '1:1':(1,1), '4:3':(4,3), '3:4':(3,4)}
GENERATION_SIZES = {'standard':960,'light':768,'very-light':256,'high':1280,'very-high':1536}
GENERATION_SIZE_LABELS = {'standard':'Standard','light':'Light','very-light':'Very Light','high':'High','very-high':'Very High'}


def image_geometry(resolution, aspect_ratio='16:9', generation_size='standard'):
    if resolution not in RESOLUTIONS or aspect_ratio not in ASPECT_RATIOS or generation_size not in GENERATION_SIZES:
        raise ValueError('Invalid resolution, aspect ratio, or generation size.')
    x,y = ASPECT_RATIOS[aspect_ratio]
    edge = max(RESOLUTIONS[resolution])
    width,height = (edge,round(edge*y/x)) if x>=y else (round(edge*x/y),edge)
    base_edge = GENERATION_SIZES[generation_size]
    base_width = ((round(base_edge*x/max(x,y))+15)//16)*16
    base_height = ((round(base_edge*y/max(x,y))+15)//16)*16
    if width*base_height >= height*base_width:
        up_width,up_height = width,(width*base_height+base_width-1)//base_width
    else:
        up_width,up_height = (height*base_width+base_height-1)//base_height,height
    return {'width':width,'height':height,'base_width':base_width,'base_height':base_height,
            'upscaled_width':up_width,'upscaled_height':up_height}


PROFILES = {
 'klein': {'label':'FLUX.2 Klein 4B','steps':'4','cfg':'1','schedule':['--scheduler','flux2'], 'family':'klein','references':True},
 'z-image-turbo': {'label':'Z-Image Turbo','steps':'9','cfg':'1','schedule':[], 'family':'z-image-turbo','references':False},
 'qwen-image21-experimental': {'label':'Qwen Image 2.1 · ChatR Labs Turbo', 'steps':'8','cfg':'1', 'schedule':['--scheduler','simple'], 'family':'qwen_image21', 'references':True, 'lora':'chatrlabs-omni-turbo-8step-fp32.safetensors', 'components':{'diffusion':'qwen_image21','encoder':'qwen3vl-8b','vae':'qwen','vision':'qwen3vl-8b'}},
}
SD_DEFAULT = {'steps':9, 'cfg':1.0, 'sampler':'euler', 'scheduler':'auto',
              'vae_tiling':True, 'vae_tile_size':0, 'mmap':True}
# The final model evaluation in both short Z-Image schedules starts at 0.22.
Z_IMAGE_PRESET_SIGMAS = {
    'z-image-4': (1.0, 0.9001200199127197, 0.62, 0.22, 0.0),
    'z-image-5': (1.0, 0.9001200199127197, 0.7503749132156372, 0.5009990334510803, 0.22, 0.0),
}
SD_DEFAULTS = {
    'default': dict(SD_DEFAULT),
    **{key: {**SD_DEFAULT, 'steps': len(sigmas) - 1} for key, sigmas in Z_IMAGE_PRESET_SIGMAS.items()},
    'klein': {**SD_DEFAULT, 'steps': 4, 'scheduler': 'flux2'},
    'klein-3': {**SD_DEFAULT, 'steps': 3, 'scheduler': 'flux2'},
    'qwen-image21-experimental': {**SD_DEFAULT, 'steps': 8, 'cfg': 1.0, 'scheduler': 'simple'},
    # Deliberately only reduce the denoising count; all other parameters,
    # including the ChatR Labs Turbo LoRA and scheduler, match the 8-step base.
    'qwen-image21-4': {**SD_DEFAULT, 'steps': 4, 'cfg': 1.0, 'scheduler': 'simple'},
}
SD_PROFILE_FAMILIES = {
    'default': 'z-image-turbo',
    **dict.fromkeys(Z_IMAGE_PRESET_SIGMAS, 'z-image-turbo'),
    'klein': 'klein',
    'klein-3': 'klein',
    'qwen-image21-experimental': 'qwen-image21-experimental',
    'qwen-image21-4': 'qwen-image21-experimental',
}
MODEL_DEFAULTS = {'z-image-turbo':{'diffusion':'z_image_turbo-Q8_0.gguf','encoder':'Qwen3-4B-Instruct-2507-Q4_K_M.gguf','vae':'ae.safetensors'}, 'klein':{'diffusion':'flux-2-klein-4b-Q8_0.gguf','encoder':'Qwen3-4B-Q4_K_M.gguf','vae':'flux2-vae.safetensors'}}
CUSTOM_DEFAULTS = {'z-image-turbo':dict(SD_DEFAULT), 'klein':dict(SD_DEFAULTS['klein'])}

# All three models are first-class popAI profiles. Keep the original internal
# Qwen profile key to preserve saved settings and existing jobs without migration.
MODEL_DEFAULTS['qwen-image21-experimental'] = {
    'diffusion':'qwen-image-2.1-step90000-Q8_0.gguf',
    'encoder':'Qwen3VL-8B-Instruct-Q4_K_M.gguf',
    'vae':'qwen_image_2.1_vae_bf16.safetensors',
    'vision':'mmproj-Qwen3VL-8B-Instruct-F16.gguf',
}
PROFILE_FILES = MODEL_DEFAULTS
CUSTOM_DEFAULTS['qwen-image21-experimental'] = dict(SD_DEFAULTS['qwen-image21-experimental'])


def component_family(family, role):
    return PROFILES.get(family,{}).get('components',{}).get(role, 'qwen3-4b' if role=='encoder' else family)
SAMPLERS = ('euler','euler_a','heun','dpm2','dpm++2m','dpm++2s_a','ddim_trailing','lcm')
SCHEDULERS = ('auto','discrete','karras','exponential','simple','sgm_uniform','flux2')


def normalize_sd(settings):
    if isinstance(settings,dict):
        settings = {key:value for key,value in settings.items() if key != 'seed'}
    if not isinstance(settings,dict) or set(settings)-set(SD_DEFAULT):
        raise ValueError('Invalid Stable Diffusion settings.')
    result = {**SD_DEFAULT,**settings}
    if type(result['steps']) is not int or not 1 <= result['steps'] <= 150:
        raise ValueError('Use between 1 and 150 steps.')
    if type(result['cfg']) not in (float,int) or not math.isfinite(result['cfg']) or not 0 <= result['cfg'] <= 30:
        raise ValueError('CFG must be between 0 and 30.')
    if result['sampler'] not in SAMPLERS or result['scheduler'] not in SCHEDULERS:
        raise ValueError('Invalid sampler or scheduler.')
    if any(type(result[k]) is not bool for k in ('vae_tiling','mmap')):
        raise ValueError('Choose whether to enable mmap and VAE tiling.')
    tile = result['vae_tile_size']
    if type(tile) is not int or tile != 0 and (not 64 <= tile <= 2048 or tile % 64):
        raise ValueError('Set the VAE tile size to Auto (0) or a multiple of 64 between 64 and 2048.')
    return result


def _klein_last_two_sigmas(width, height):
    # Match Flux2Scheduler::compute_empirical_mu for four evaluations.
    tokens = (width // 16) * (height // 16)
    mu_200 = 0.00016927 * tokens + 0.45666666
    mu = mu_200
    if tokens <= 4300:
        mu_10 = 0.0000873809524 * tokens + 1.89833333
        mu += (200 - 4) * (mu_10 - mu_200) / 190
    shifted = math.exp(mu)
    # The third and fourth evaluations use t = 0.5 and t = 0.25.
    return shifted / (shifted + 1.0), shifted / (shifted + 3.0)


def generation_profile(settings, family="z-image-turbo", *, sd_profile=None, base_size=None):
    result = {**PROFILES[family],**settings}
    result['steps'],result['cfg'] = str(settings['steps']),str(settings['cfg'])
    result['schedule'] = [] if settings['scheduler']=='auto' else ['--scheduler',settings['scheduler']]
    sigmas = Z_IMAGE_PRESET_SIGMAS.get(sd_profile) if family == 'z-image-turbo' else None
    if family == 'klein':
        if sd_profile == 'klein-3':
            third, fourth = _klein_last_two_sigmas(*base_size)
            sigmas = (1.0, third, fourth, 0.0)
    if sigmas is not None:
        result['schedule'] = ['--sigmas', ','.join(map(str, sigmas))]
    return result
