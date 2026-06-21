"""Seed the DSA question bank with classic problems and test cases."""
import json
from datetime import datetime, timezone
from app.db import get_connection

# Each problem: slug, title, difficulty, category, description, examples,
# constraints, starter_code_python, starter_code_js, test_cases (list of dicts)
QUESTIONS = [
    {
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "category": "Arrays",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        "examples": [
            {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]", "explanation": "nums[0] + nums[1] == 9"},
            {"input": "nums = [3,2,4], target = 6", "output": "[1,2]", "explanation": "nums[1] + nums[2] == 6"},
        ],
        "constraints": "2 <= nums.length <= 10^4",
        "starter_code_python": "def solve(nums, target):\n    # return list of two indices\n    pass\n",
        "starter_code_js": "function solve(nums, target) {\n  // return array of two indices\n}\n",
        "tests": [
            {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"input": [[3, 2, 4], 6], "expected": [1, 2]},
            {"input": [[3, 3], 6], "expected": [0, 1]},
        ],
    },
    {
        "slug": "valid-parentheses",
        "title": "Valid Parentheses",
        "difficulty": "Easy",
        "category": "Strings",
        "description": "Given a string s containing just the characters '()[]{}', determine if the input string is valid.",
        "examples": [
            {"input": "s = \"()\"", "output": "true", "explanation": "matched"},
            {"input": "s = \"(]\"", "output": "false", "explanation": "mismatched"},
        ],
        "constraints": "1 <= s.length <= 10^4",
        "starter_code_python": "def solve(s):\n    # return True or False\n    pass\n",
        "starter_code_js": "function solve(s) {\n  // return true or false\n}\n",
        "tests": [
            {"input": ["()"], "expected": True},
            {"input": ["(]"], "expected": False},
            {"input": ["([])"], "expected": True},
        ],
    },
    {
        "slug": "reverse-linked-list",
        "title": "Reverse Linked List",
        "difficulty": "Easy",
        "category": "Linked Lists",
        "description": "Given an array representing a linked list, return the reversed list as an array.",
        "examples": [
            {"input": "head = [1,2,3,4,5]", "output": "[5,4,3,2,1]", "explanation": "reversed"},
        ],
        "constraints": "0 <= n <= 5000",
        "starter_code_python": "def solve(head):\n    # head is a list; return reversed list\n    pass\n",
        "starter_code_js": "function solve(head) {\n  // head is an array; return reversed array\n}\n",
        "tests": [
            {"input": [[1, 2, 3, 4, 5]], "expected": [5, 4, 3, 2, 1]},
            {"input": [[1, 2]], "expected": [2, 1]},
            {"input": [[]], "expected": []},
        ],
    },
    {
        "slug": "max-subarray",
        "title": "Maximum Subarray",
        "difficulty": "Medium",
        "category": "DP",
        "description": "Given an integer array nums, find the subarray with the largest sum and return its sum.",
        "examples": [
            {"input": "nums = [-2,1,-3,4,-1,2,1,-5,4]", "output": "6", "explanation": "[4,-1,2,1] has sum 6"},
        ],
        "constraints": "1 <= nums.length <= 10^5",
        "starter_code_python": "def solve(nums):\n    # return the maximum subarray sum\n    pass\n",
        "starter_code_js": "function solve(nums) {\n  // return the maximum subarray sum\n}\n",
        "tests": [
            {"input": [[-2, 1, -3, 4, -1, 2, 1, -5, 4]], "expected": 6},
            {"input": [[1]], "expected": 1},
            {"input": [[5, 4, -1, 7, 8]], "expected": 23},
        ],
    },
    {
        "slug": "binary-search",
        "title": "Binary Search",
        "difficulty": "Easy",
        "category": "Searching",
        "description": "Given a sorted array nums and a target, return the index of target or -1 if not found.",
        "examples": [
            {"input": "nums = [-1,0,3,5,9,12], target = 9", "output": "4", "explanation": "index 4"},
        ],
        "constraints": "1 <= nums.length <= 10^4",
        "starter_code_python": "def solve(nums, target):\n    # return index or -1\n    pass\n",
        "starter_code_js": "function solve(nums, target) {\n  // return index or -1\n}\n",
        "tests": [
            {"input": [[-1, 0, 3, 5, 9, 12], 9], "expected": 4},
            {"input": [[-1, 0, 3, 5, 9, 12], 2], "expected": -1},
            {"input": [[5], 5], "expected": 0},
        ],
    },
    {
        "slug": "palindrome-check",
        "title": "Palindrome Check",
        "difficulty": "Easy",
        "category": "Strings",
        "description": "Given a string s, return True if it is a palindrome, ignoring case.",
        "examples": [
            {"input": "s = \"racecar\"", "output": "true", "explanation": "same forwards and backwards"},
        ],
        "constraints": "1 <= s.length <= 10^5",
        "starter_code_python": "def solve(s):\n    # return True or False\n    pass\n",
        "starter_code_js": "function solve(s) {\n  // return true or false\n}\n",
        "tests": [
            {"input": ["racecar"], "expected": True},
            {"input": ["hello"], "expected": False},
            {"input": ["Aba"], "expected": True},
        ],
    },
    {
        "slug": "fibonacci",
        "title": "Fibonacci Number",
        "difficulty": "Easy",
        "category": "DP",
        "description": "Return the n-th Fibonacci number where F(0)=0, F(1)=1.",
        "examples": [
            {"input": "n = 5", "output": "5", "explanation": "0,1,1,2,3,5"},
        ],
        "constraints": "0 <= n <= 30",
        "starter_code_python": "def solve(n):\n    # return the n-th fibonacci number\n    pass\n",
        "starter_code_js": "function solve(n) {\n  // return the n-th fibonacci number\n}\n",
        "tests": [
            {"input": [5], "expected": 5},
            {"input": [0], "expected": 0},
            {"input": [10], "expected": 55},
        ],
    },
    {
        "slug": "merge-sorted-arrays",
        "title": "Merge Sorted Arrays",
        "difficulty": "Easy",
        "category": "Arrays",
        "description": "Given two sorted arrays a and b, return a single merged sorted array.",
        "examples": [
            {"input": "a = [1,3,5], b = [2,4,6]", "output": "[1,2,3,4,5,6]", "explanation": "merged sorted"},
        ],
        "constraints": "0 <= len <= 10^4",
        "starter_code_python": "def solve(a, b):\n    # return merged sorted list\n    pass\n",
        "starter_code_js": "function solve(a, b) {\n  // return merged sorted array\n}\n",
        "tests": [
            {"input": [[1, 3, 5], [2, 4, 6]], "expected": [1, 2, 3, 4, 5, 6]},
            {"input": [[], [1, 2]], "expected": [1, 2]},
            {"input": [[1], []], "expected": [1]},
        ],
    },
    {
        "slug": "count-islands",
        "title": "Number of Islands",
        "difficulty": "Medium",
        "category": "Graphs",
        "description": "Given a 2D grid of 1s (land) and 0s (water), count the number of islands.",
        "examples": [
            {"input": "grid = [[1,1,0],[0,1,0],[0,0,1]]", "output": "2", "explanation": "two islands"},
        ],
        "constraints": "1 <= m, n <= 300",
        "starter_code_python": "def solve(grid):\n    # return number of islands\n    pass\n",
        "starter_code_js": "function solve(grid) {\n  // return number of islands\n}\n",
        "tests": [
            {"input": [[[1, 1, 0], [0, 1, 0], [0, 0, 1]]], "expected": 2},
            {"input": [[[1, 1, 1], [1, 1, 1]]], "expected": 1},
            {"input": [[[0, 0], [0, 0]]], "expected": 0},
        ],
    },
    {
        "slug": "longest-common-prefix",
        "title": "Longest Common Prefix",
        "difficulty": "Easy",
        "category": "Strings",
        "description": "Find the longest common prefix string amongst an array of strings.",
        "examples": [
            {"input": "strs = [\"flower\",\"flow\",\"flight\"]", "output": "\"fl\"", "explanation": "common prefix"},
        ],
        "constraints": "1 <= strs.length <= 200",
        "starter_code_python": "def solve(strs):\n    # return the longest common prefix string\n    pass\n",
        "starter_code_js": "function solve(strs) {\n  // return the longest common prefix string\n}\n",
        "tests": [
            {"input": [["flower", "flow", "flight"]], "expected": "fl"},
            {"input": [["dog", "racecar", "car"]], "expected": ""},
            {"input": [["abc", "abc"]], "expected": "abc"},
        ],
    },
]


def seed_dsa_questions():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        for q in QUESTIONS:
            cursor.execute("SELECT 1 FROM dsa_questions WHERE slug = ?", (q["slug"],))
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO dsa_questions
                (slug, title, difficulty, category, description, examples, constraints,
                 starter_code_python, starter_code_js, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q["slug"], q["title"], q["difficulty"], q["category"], q["description"],
                    json.dumps(q["examples"]), q["constraints"],
                    q["starter_code_python"], q["starter_code_js"], now,
                ),
            )
            for i, tc in enumerate(q["tests"]):
                cursor.execute(
                    """
                    INSERT INTO dsa_test_cases
                    (question_slug, input, expected_output, is_hidden, order_index)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        q["slug"], json.dumps(tc["input"]), json.dumps(tc["expected"]),
                        1 if i >= 2 else 0, i,
                    ),
                )
        conn.commit()
    finally:
        conn.close()
