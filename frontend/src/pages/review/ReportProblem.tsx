import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { reportProblem } from '../../api/client'
import { errorMessage } from '../../api/errors'

/**
 * Story 4.4: the parent's "Báo lỗi" action with an optional note. An open parent report
 * hides the Problem from the child until it is resolved in Duyệt nội dung.
 */
export default function ReportProblem({
  problemId,
  reported = false,
}: {
  problemId: string
  reported?: boolean
}) {
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const send = useMutation({
    mutationFn: () => reportProblem(problemId, note.trim()),
    onSuccess: () => {
      setNote('')
      void queryClient.invalidateQueries({ queryKey: ['review'] })
      void queryClient.invalidateQueries({ queryKey: ['parent', 'dashboard'] })
    },
  })
  return (
    <div className="report-problem">
      <label>
        Ghi chú (không bắt buộc)
        <input
          type="text"
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.preventDefault()
          }}
        />
      </label>
      <button type="button" disabled={send.isPending} onClick={() => send.mutate()}>
        Báo lỗi
      </button>
      {(send.isSuccess || reported) && (
        <p role={send.isSuccess ? 'status' : undefined}>
          Đã báo lỗi. Bài này được ẩn với bé cho đến khi xử lý xong.
        </p>
      )}
      {send.isError && (
        <p role="alert" className="form-error">
          {errorMessage(send.error)}
        </p>
      )}
    </div>
  )
}
