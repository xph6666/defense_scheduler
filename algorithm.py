def generate_schedule(teachers, students, rooms, rules):
    """
    智能排期算法原型 (增强版)
    根据输入的教师、学生、教室数据生成分组。
    """
    if not teachers or not students:
        return {
            "groups": [],
            "conflicts": [{"type": "no_data", "description": "教师或学生数据不足，无法生成排期"}]
        }

    groups = []
    conflicts = []
    
    # 简单的分堆算法：每组 1 个组长，1 个秘书，2 个专家，5 个学生
    students_per_group = 5
    num_groups = (len(students) + students_per_group - 1) // students_per_group
    
    # 角色分类
    leaders = [t for t in teachers if "组长" in (t.get('roles') or []) or "主席" in (t.get('roles') or [])]
    secretaries = [t for t in teachers if "秘书" in (t.get('roles') or [])]
    others = [t for t in teachers if t not in leaders and t not in secretaries]
    
    # 如果分类数据不足，直接使用全部教师
    if not leaders: leaders = teachers
    if not secretaries: secretaries = teachers
    
    for i in range(num_groups):
        group_id = f"G{i+1:02d}"
        
        # 选择教师
        chair = leaders[i % len(leaders)]
        secretary = secretaries[i % len(secretaries)]
        
        # 选择专家 (排除掉组长和秘书)
        experts = []
        available_experts = [t for t in teachers if t['id'] != chair['id'] and t['id'] != secretary['id']]
        if len(available_experts) >= 2:
            experts = random_sample(available_experts, 2)
        elif available_experts:
            experts = available_experts
            
        # 选择学生
        start_idx = i * students_per_group
        end_idx = min(start_idx + students_per_group, len(students))
        group_students = students[start_idx:end_idx]
        
        # 选择教室
        room = rooms[i % len(rooms)] if rooms else None
        
        groups.append({
            "group_id": group_id,
            "time": f"{rules.get('start_date', '2025-05-10')} 09:00-12:00",
            "room_id": room['id'] if room else None,
            "campus": room['campus'] if room else "未分配",
            "chair_id": chair['id'],
            "expert_ids": [t['id'] for t in experts],
            "secretary_id": secretary['id'],
            "student_ids": [s['id'] for s in group_students]
        })

    return {
        "groups": groups,
        "conflicts": conflicts
    }

def random_sample(items, k):
    import random
    if len(items) <= k:
        return items
    return random.sample(items, k)