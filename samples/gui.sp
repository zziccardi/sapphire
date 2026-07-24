/* GUI component tree */

// 1. Nominal Enum for Component States
enum WidgetState {
  Default,
  Hovered,
  Pressed,
  Disabled,
}

// 2. Opt-in Prototypal Theme (Base Style Archetype)
proto ComponentTheme {
  var bg_color: String = "#FFFFFF";
  var text_color: String = "#111111";
  var corner_radius: float = 4.0;
  var padding: int = 12;
}

// 3. Widget Contract Trait
trait Widget {
  func render();
  func handle_click();
}

// 4. GUI Button Component Struct
struct Button {
  let id: String;
  var label: String;
  var state: WidgetState = WidgetState.Default;
  var theme: ComponentTheme;
  var parent: Button?;                // Optional parent widget reference
  var on_click: ((String) -> void)?;  // Optional click listener callback
}

impl Button {
  // Const method: does not mutate self
  const func get_background(): String {
    if self.state == WidgetState.Disabled {
      return "#E0E0E0";
    }
    return self.theme.bg_color;
  }

  // Mutating method
  func set_state(new_state: WidgetState) {
    self.state = new_state;
  }

  func trigger_click() {
    if self.state == WidgetState.Disabled {
      return;
    }

    // Safely invoke optional closure via optional chaining syntax
    self.on_click?.(self.id);
  }
}

// Implement Widget contract for Button
impl Widget for Button {
  func render() {
    let bg = self.get_background();
    print("Rendering Button [" + self.id + "] with label '" + self.label +
          "' and bg: " + bg);
  }

  func handle_click() {
    self.trigger_click();
  }
}

// --------------------------------------------------
// Usage Demonstration
// --------------------------------------------------

// Base Light Theme
var light_theme = ComponentTheme {
  bg_color = "#F0F0F4",
  text_color = "#222222",
  corner_radius = 6.0,
  padding = 10,
};

// Create a Primary Action Button style by cloning the base theme
let primary_button_theme = clone light_theme {
  self.bg_color = "#3B82F6";  // Shadowed locally for primary buttons
  self.text_color = "#FFFFFF";
};

// Construct a GUI Button component using named struct initializer
var submit_btn = Button {
  id = "btn_submit",
  label = "Submit Form",
  theme = primary_button_theme,
  parent = none,
  on_click = button_id -> print("Button clicked: " + button_id),
};

// Render and interact safely
// Output: Rendering Button [btn_submit] ... bg: #3B82F6
submit_btn.render();
// Output: Button clicked: btn_submit
submit_btn.handle_click();

// Optional unwrapping demo
if let parent_widget = submit_btn.parent {
  print("Has parent widget");
} else {
  print("Root widget (no parent)");
}
