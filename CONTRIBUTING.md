# 😎 Contributing Guidelines

Welcome to the exciting world of contribution! We've laid out some enchanting guidelines to make your journey smoother. 🌟

## 🔥 Submitting Contributions
Here's a magical walkthrough to get your contributions soaring high!

### 🧐 Choose an Issue/ Create an Issue

- Look for a quest on our issue board, or embark on your own by creating one.
- Leave a comment on the quest you'd like to embark on and wait for your magical assignment.

### 🪄 Fork the Repository

- Begin your adventure by clicking the "Fork" button. This creates a personal copy of the repository in your GitHub treasure chest.

### 🚀 Clone the Forked Repository

- Once you've found your treasure, clone it to your local wizard's chamber.
- Click on the "Code" button and copy the link from the dropdown menu.

```bash
git clone https://github.com/<your-username>/<repo-name>
```

- Don't forget to keep a map to the original project with the `upstream` remote.

```bash
cd <repo-name>
git remote add upstream https://github.com/<upstream-owner>/<repo-name>
git remote -v # Check the mystical remotes for this repository
```

- If you've already found a treasure before, update it before setting sail.

```bash
git remote update
git checkout <branch-name>
git rebase upstream/<branch-name>
```

### 🌠 Create a New Branch

- Always create a new branch, give it a name that describes your quest.

```bash
# This spell creates a new branch and takes you there.
git checkout -b branch_name
```

### 🪄 Work on the Assigned Quest

- Set forth on your quest, make changes to the enchanted files/folders.
- After completing your quest, add the spoils to your branch.

```bash
# Add all newly discovered treasures to the Branch_Name.
git add .

# Or add specific treasures to Branch_Name.
git add <file name>
```

### 📜 Commit the Changes

- Document your discoveries in your magical tome with descriptive messages.

```bash
git commit -m "My mystical message"
```

- Remember, a Pull Request should only contain one epic discovery.

### 🚁 Push the Changes

- Send your magical discoveries to your remote repository.

```bash
git push origin branch_name
```

### 🎯 Create a Pull Request

- Visit your repository in the realm of the internet and click "compare and pull request."
- Write a captivating title and an adventurous description for your Pull Request.
- Your Pull Request will be reviewed by the wise maintainers and, once approved, merged into the original code.

### ✨ Congratulations!

You've joined the league of extraordinary contributors. May your journey be filled with magical adventures and enchanting discoveries. Happy Hacking! 🧙‍♂️✨🚀
