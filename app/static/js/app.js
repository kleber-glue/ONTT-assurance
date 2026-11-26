document.querySelectorAll(".drop-zone input[type=file]").forEach((input) => {
    input.addEventListener("change", () => {
        const label = input.closest(".drop-zone");
        if (input.files.length) {
            label.querySelector("strong").textContent = input.files[0].name;
        }
    });
});

const correspondenceContainer = document.querySelector("#correspondence-container");
if (correspondenceContainer) {
    const correspondenceTemplate = document.querySelector("#correspondence-template");
    const addCorrespondenceButton = document.querySelector("#add-correspondence");
    let nextCorrespondenceIndex = correspondenceContainer.querySelectorAll(
        'input[name="correspondence_ids"]'
    ).length;

    const updateTableRemovalButtons = (correspondence) => {
        const tables = correspondence.querySelectorAll(".table-entry");
        tables.forEach((table) => {
            table.querySelector(".remove-table").disabled = tables.length === 1;
        });
    };

    correspondenceContainer.querySelectorAll(".correspondence-section").forEach(
        updateTableRemovalButtons
    );

    addCorrespondenceButton.addEventListener("click", () => {
        const section = correspondenceTemplate.innerHTML.replace(
            /__GROUP_INDEX__/g,
            String(nextCorrespondenceIndex++)
        );
        correspondenceContainer.insertAdjacentHTML("beforeend", section);
    });

    correspondenceContainer.addEventListener("click", (event) => {
        const addTableButton = event.target.closest(".add-table");
        if (addTableButton) {
            const correspondence = addTableButton.closest(".correspondence-section");
            const tableIndex = Number(correspondence.dataset.nextTableIndex);
            const template = correspondence.querySelector(".table-template");
            const table = template.innerHTML.replace(
                /__TABLE_INDEX__/g,
                String(tableIndex)
            );
            correspondence.querySelector(".table-container").insertAdjacentHTML(
                "beforeend",
                table
            );
            correspondence.dataset.nextTableIndex = String(tableIndex + 1);
            updateTableRemovalButtons(correspondence);
            return;
        }

        const removeTableButton = event.target.closest(".remove-table");
        if (removeTableButton && !removeTableButton.disabled) {
            const correspondence = removeTableButton.closest(".correspondence-section");
            removeTableButton.closest(".table-entry").remove();
            updateTableRemovalButtons(correspondence);
            return;
        }

        const removeCorrespondenceButton = event.target.closest(
            ".remove-correspondence"
        );
        if (removeCorrespondenceButton) {
            removeCorrespondenceButton.closest(".correspondence-section").remove();
        }
    });
}
