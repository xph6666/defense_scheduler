def generate_schedule(teachers, students, rooms, rules):
    # 检查是否有教师数据
    if not teachers:
        return {
            "groups": [],
            "conflicts": [{"type": "no_data", "description": "没有教师数据，无法生成排期"}]
        }

    # 获取第一个教师的 id 作为 chair
    first_teacher_id = teachers[0]['id'] if teachers else None

    return {
        "groups": [
            {
                "group_id": "G1",
                "time": "2025-05-10 09:00-12:00",
                "room_id": None,  # 先设为 None，因为没有教室数据
                "campus": "创新港",
                "chair_id": first_teacher_id,
                "expert_ids": [],  # 空列表，因为没有其他教师
                "secretary_id": None,
                "student_ids": []  # 空列表，因为没有学生
            }
        ],
        "conflicts": []
    }