"""评价模型管理路由"""
from flask import Blueprint, request, jsonify
from flask_login import login_required
from ..models import db, JudgeModel

judge_bp = Blueprint('judge', __name__)


@judge_bp.route('/', methods=['GET'])
@login_required
def list_judge_models():
    """获取所有评价模型"""
    models = JudgeModel.query.order_by(JudgeModel.created_at.desc()).all()
    return jsonify({'judge_models': [m.to_dict() for m in models]}), 200


@judge_bp.route('/<int:model_id>', methods=['GET'])
@login_required
def get_judge_model(model_id):
    """获取单个评价模型详情"""
    model = JudgeModel.query.get_or_404(model_id)
    return jsonify({'judge_model': model.to_dict()}), 200


@judge_bp.route('/', methods=['POST'])
@login_required
def create_judge_model():
    """创建评价模型"""
    data = request.get_json()
    for field in ('name', 'url', 'api_key', 'model'):
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    jm = JudgeModel(
        name=data['name'].strip(),
        url=data['url'].strip(),
        api_key=data['api_key'].strip(),
        model=data['model'].strip(),
    )
    db.session.add(jm)
    db.session.commit()
    return jsonify({'judge_model': jm.to_dict()}), 201


@judge_bp.route('/<int:model_id>', methods=['PUT'])
@login_required
def update_judge_model(model_id):
    """更新评价模型"""
    jm = JudgeModel.query.get_or_404(model_id)
    data = request.get_json()
    if 'name' in data:
        jm.name = data['name'].strip()
    if 'url' in data:
        jm.url = data['url'].strip()
    if 'api_key' in data and data['api_key'] != '******':
        jm.api_key = data['api_key'].strip()
    if 'model' in data:
        jm.model = data['model'].strip()
    db.session.commit()
    return jsonify({'judge_model': jm.to_dict()}), 200


@judge_bp.route('/<int:model_id>', methods=['DELETE'])
@login_required
def delete_judge_model(model_id):
    """删除评价模型"""
    jm = JudgeModel.query.get_or_404(model_id)
    db.session.delete(jm)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200
