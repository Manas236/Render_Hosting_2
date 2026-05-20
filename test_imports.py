import sys
import importlib.util

def test_imports():
    print("starting test...")
    try:
        print("importing login")
        import login
        print("importing dashboard")
        import dashboard
        print("importing codeview")
        import codeview
        print("importing extractor")
        import extractor
        print("importing batch_extractor")
        import batch_extractor
        print("importing upload_image")
        import upload_image
        
        print("importing day8_v2_editor")
        spec = importlib.util.spec_from_file_location("day8_v2_editor", "editor_day8_v2.py")
        day8_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(day8_module)

        print("importing day9_editor")
        spec_day9 = importlib.util.spec_from_file_location("day9_editor", "editor(for Day9.html).py")
        day9_module = importlib.util.module_from_spec(spec_day9)
        spec_day9.loader.exec_module(day9_module)

        print("importing editor_day6temp")
        import editor_day6temp

        print("importing editor_template1")
        import editor_template1

        print("importing day11_editor")
        spec_day11 = importlib.util.spec_from_file_location("day11_editor", "app11.py")
        day11_module = importlib.util.module_from_spec(spec_day11)
        spec_day11.loader.exec_module(day11_module)

        print("importing day12_editor")
        spec_day12 = importlib.util.spec_from_file_location("day12_editor", "editor(for Day12.html).py")
        day12_module = importlib.util.module_from_spec(spec_day12)
        spec_day12.loader.exec_module(day12_module)

        print("importing day15_editor")
        spec_day15 = importlib.util.spec_from_file_location("day15_editor", "editor(for Day15.html).py")
        day15_module = importlib.util.module_from_spec(spec_day15)
        spec_day15.loader.exec_module(day15_module)

        print("importing day12_2_editor")
        spec_day12_2 = importlib.util.spec_from_file_location("day12_2_editor", "editor(for Day12(2).html).py")
        day12_2_module = importlib.util.module_from_spec(spec_day12_2)
        spec_day12_2.loader.exec_module(day12_2_module)
        
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_imports()
