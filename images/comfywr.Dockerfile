FROM local

ADD https://huggingface.co/lllyasviel/Annotators/resolve/main/sk_model.pth?download=true /workdir/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/sk_model.pth
ADD https://huggingface.co/lllyasviel/Annotators/resolve/main/sk_model2.pth?download=true /workdir/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/sk_model2.pth

COPY --from=root sd_models /workdir/ComfyUI/models
COPY --from=root sd_scripts /workdir/sd_scripts

COPY --from=comfywr-root ComfyUI /workdir/ComfyUI
COPY --from=comfywr-root custom_nodes /workdir/custom_nodes
COPY --from=comfywr-root comfywr /workdir/comfywr
