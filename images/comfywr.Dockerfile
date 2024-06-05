FROM local

COPY --from=root sd_models /workdir/ComfyUI/models
COPY --from=root sd_scripts /workdir/sd_scripts

COPY --from=comfywr-root ComfyUI /workdir/ComfyUI
COPY --from=comfywr-root custom_nodes /workdir/custom_nodes
COPY --from=comfywr-root comfywr /workdir/comfywr
COPY --from=comfywr-root custom_nodes/ComfyUI_UltimateSDUpscale /workdir/ComfyUI/custom_nodes/ComfyUI_UltimateSDUpscale

ADD https://huggingface.co/lllyasviel/Annotators/resolve/main/sk_model.pth?download=true /workdir/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/sk_model.pth
ADD https://huggingface.co/lllyasviel/Annotators/resolve/main/sk_model2.pth?download=true /workdir/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/sk_model2.pth

RUN apt install git git-lfs -y

RUN git -c 'lfs.fetchexclude=*.bin,*fp16*' clone https://huggingface.co/prs-eth/marigold-v1-0 /workdir/ComfyUI/models/diffusers/Marigold
#RUN git -c 'lfs.fetchexclude=*.bin,*fp16*' clone https://huggingface.co/prs-eth/marigold-lcm-v1-0 /workdir/ComfyUI/models/diffusers/marigold-lcm-v1-0