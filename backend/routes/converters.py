"""
攻击变换器 API 路由

提供可用变换器的查询接口，前端可动态获取变换器列表供用户选择。
"""
from flask import Blueprint, jsonify
from flask_login import login_required
from ..converters.text_converters import list_available_converters, ConverterRegistry

converters_bp = Blueprint('converters', __name__)


@converters_bp.route('/', methods=['GET'])
@login_required
def list_converters():
    """列出所有可用的 prompt 攻击变换器"""
    converters = list_available_converters()
    return jsonify({'converters': converters}), 200


@converters_bp.route('/tags', methods=['GET'])
@login_required
def list_tags():
    """列出所有变换器的标签分类"""
    all_converters = ConverterRegistry.list_all()
    tags = sorted(set(tag for c in all_converters for tag in c.tags))
    return jsonify({'tags': tags}), 200
