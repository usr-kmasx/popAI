"""Single source of profile defaults and output presets for API and UI."""
RESOLUTIONS = {'720p': (1280,720), '900p': (1600,900), '1080p': (1920,1080),
               '1440p': (2560,1440), '1800p': (3200,1800), '2160p': (3840,2160)}
ASPECT_RATIOS = {'16:9':(16,9), '9:16':(9,16), '9:20':(9,20),
                 '1:1':(1,1), '4:3':(4,3), '3:4':(3,4)}
GENERATION_SIZES = {'standard':960,'light':768,'very-light':256,'high':1280,'very-high':1536}
GENERATION_SIZE_LABELS = {'standard':'Padrão','light':'Leve','very-light':'Muito leve','high':'Alto','very-high':'Muito alto'}


def image_geometry(resolution, aspect_ratio='16:9', generation_size='standard'):
    if resolution not in RESOLUTIONS or aspect_ratio not in ASPECT_RATIOS or generation_size not in GENERATION_SIZES:
        raise ValueError('Resolução, proporção ou tamanho de geração inválido.')
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
 'flux3-klein': {'label':'FLUX 3 Image Klein','steps':'16','cfg':'1','schedule':['--scheduler','discrete'], 'family':'flux3-klein','references':True, 'components':{'encoder':'qwen3vl-4b','vae':'klein'}},
}
SD_DEFAULT = {'steps':9, 'cfg':1.0, 'sampler':'euler', 'scheduler':'auto',
              'vae_tiling':True, 'vae_tile_size':0, 'mmap':True}
SD_DEFAULTS = {'default':dict(SD_DEFAULT), 'klein':{**SD_DEFAULT,'steps':4,'scheduler':'flux2'}, 'flux3-klein':{**SD_DEFAULT,'steps':16,'scheduler':'discrete'}}
MODEL_DEFAULTS = {'z-image-turbo':{'diffusion':'z_image_turbo-Q8_0.gguf','encoder':'Qwen3-4B-Instruct-2507-Q4_K_M.gguf','vae':'ae.safetensors'}, 'klein':{'diffusion':'flux-2-klein-4b-Q8_0.gguf','encoder':'Qwen3-4B-Q4_K_M.gguf','vae':'flux2-vae.safetensors'}}
CUSTOM_DEFAULTS = {'z-image-turbo':dict(SD_DEFAULT), 'klein':dict(SD_DEFAULTS['klein'])}
MODEL_DEFAULTS['flux3-klein'] = {'diffusion':'flux3-image-klein-Q8_0.gguf','encoder':'Qwen3VL-4B-Instruct-Q4_K_M.gguf','vae':'flux2-vae.safetensors'}
CUSTOM_DEFAULTS['flux3-klein'] = dict(SD_DEFAULTS['flux3-klein'])


def component_family(family, role):
    return PROFILES.get(family,{}).get('components',{}).get(role, 'qwen3-4b' if role=='encoder' else family)
SAMPLERS = ('euler','euler_a','heun','dpm2','dpm++2m','dpm++2s_a','ddim_trailing','lcm')
SCHEDULERS = ('auto','discrete','karras','exponential','simple','sgm_uniform','flux2')


def normalize_sd(settings):
    import math
    if isinstance(settings,dict):
        settings = {key:value for key,value in settings.items() if key != 'seed'}
    if not isinstance(settings,dict) or set(settings)-set(SD_DEFAULT):
        raise ValueError('Ajustes de Stable Diffusion inválidos.')
    result = {**SD_DEFAULT,**settings}
    if type(result['steps']) is not int or not 1 <= result['steps'] <= 150:
        raise ValueError('Use de 1 a 150 passos.')
    if type(result['cfg']) not in (float,int) or not math.isfinite(result['cfg']) or not 0 <= result['cfg'] <= 30:
        raise ValueError('CFG deve estar entre 0 e 30.')
    if result['sampler'] not in SAMPLERS or result['scheduler'] not in SCHEDULERS:
        raise ValueError('Sampler ou scheduler inválido.')
    if any(type(result[k]) is not bool for k in ('vae_tiling','mmap')):
        raise ValueError('Ative ou desative mmap e VAE em blocos.')
    tile = result['vae_tile_size']
    if type(tile) is not int or tile != 0 and (not 64 <= tile <= 2048 or tile % 64):
        raise ValueError('Tile do VAE: automático (0) ou múltiplo de 64 entre 64 e 2048.')
    return result


def generation_profile(settings, family="z-image-turbo"):
    result = {**PROFILES[family],**settings}
    result['steps'],result['cfg'] = str(settings['steps']),str(settings['cfg'])
    result['schedule'] = [] if settings['scheduler']=='auto' else ['--scheduler',settings['scheduler']]
    return result
