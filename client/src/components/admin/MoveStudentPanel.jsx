import { useState } from "react";
import toast from "react-hot-toast";
import api from "../../utils/axios";
import { Button, SlideOver } from "../ui";
import GroupPicker from "../GroupPicker";
import { apiError } from "../../utils/helpers";
import { selectionFromPlacement } from "../../utils/structure";

const FORM_ID = "move-student-form";

/** Move a student to another cohort (and with it, its section, department and batch). */
const MoveStudentPanel = ({ user, tree, onClose, onMoved }) => {
  const current = user.placement;
  const [placement, setPlacement] = useState(() => selectionFromPlacement(current));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!placement.cohort) {
      setError("Choose the batch, department, section and cohort to move them to");
      return;
    }
    if (placement.cohort === current?.cohort?.id) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.patch(`/institution/users/${user.id}`, { cohortId: placement.cohort });
      toast.success(`Moved ${user.name} to ${data.user.placement.label}`);
      onMoved(data.user);
      onClose();
    } catch (err) {
      setError(apiError(err, "Couldn't move this student. Try again."));
      setSaving(false);
    }
  };

  return (
    <SlideOver
      open
      onClose={onClose}
      onDismiss={onClose}
      title="Change placement"
      description={`${user.name} sees every test assigned to their new batch, department, section or cohort.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={saving}>
            Move student
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4 p-5">
        <p className="text-[13px] text-slate-500">
          Currently in <span className="font-medium text-slate-800">{current?.label ?? "no cohort"}</span>. Results of
          tests they've already taken are kept.
        </p>
        <GroupPicker
          idPrefix="move"
          tree={tree}
          value={placement}
          requireCohort
          error={error}
          onChange={(next) => {
            setError("");
            setPlacement(next);
          }}
        />
      </form>
    </SlideOver>
  );
};

export default MoveStudentPanel;
