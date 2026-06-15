"""
Prompt 库管理路由
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from ..prompts.loader import PromptLoader

prompts_bp = Blueprint("prompts", __name__)
_loader = PromptLoader()


@prompts_bp.route("/", methods=["GET"])
@login_required
def list_prompts():
    """列出所有可用的 Prompt（供前端选择）"""
    category = request.args.get("category")
    tags = request.args.get("tags")
    library = request.args.get("library")

    prompts = _loader.list_prompts()

    if category:
        prompts = [p for p in prompts if p["category"] == category]
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        prompts = [p for p in prompts if any(t in p["tags"] for t in tag_list)]
    if library:
        prompts = [p for p in prompts if p["library"] == library]

    return jsonify({"prompts": prompts}), 200


@prompts_bp.route("/libraries", methods=["GET"])
@login_required
def list_libraries():
    """列出所有 Prompt 库"""
    libraries = _loader.load_all()
    result = []
    for name, lib in libraries.items():
        result.append({
            "name": name,
            "description": lib.description,
            "version": lib.version,
            "prompt_count": len(lib.prompts),
            "categories": lib.list_categories(),
        })
    return jsonify({"libraries": result}), 200


@prompts_bp.route("/categories", methods=["GET"])
@login_required
def list_categories():
    """列出所有 Prompt 分类"""
    prompts = _loader.list_prompts()
    categories = sorted(set(p["category"] for p in prompts))
    tag_set = set()
    for p in prompts:
        tag_set.update(p["tags"])
    return jsonify({"categories": categories, "tags": sorted(tag_set)}), 200


@prompts_bp.route("/<path:ref>", methods=["GET"])
@login_required
def get_prompt(ref):
    """获取单个 Prompt 详情"""
    prompt = _loader.get_prompt(ref)
    if not prompt:
        return jsonify({"error": "Prompt not found"}), 404
    return jsonify({
        "id": prompt.id,
        "name": prompt.name,
        "template": prompt.template,
        "category": prompt.category,
        "tags": prompt.tags,
        "variables": prompt.variables,
        "evaluation": prompt.evaluation,
        "metadata": prompt.metadata,
    }), 200
