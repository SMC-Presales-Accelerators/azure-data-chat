import { useMemo } from "react";
import { Stack, IconButton } from "@fluentui/react";
import DOMPurify from "dompurify";
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { vs } from 'react-syntax-highlighter/dist/esm/styles/hljs';

import styles from "./Answer.module.css";

import { ChatAppResponse, getCitationFilePath } from "../../api";
import { AnswerIcon } from "./AnswerIcon";

interface Props {
    answer: ChatAppResponse;
    isSelected?: boolean;
    isStreaming: boolean;
    onThoughtProcessClicked: () => void;
}

export const Answer = ({
    answer,
    isSelected,
    isStreaming,
    onThoughtProcessClicked,
}: Props) => {
    const messageContent = answer.choices[0].message.content;

    return (
        <Stack className={`${styles.answerContainer} ${isSelected && styles.selected}`} verticalAlign="space-between">
            <Stack.Item>
                <Stack horizontal horizontalAlign="space-between">
                    <AnswerIcon />
                    <div>
                        <IconButton
                            style={{ color: "black" }}
                            iconProps={{ iconName: "Lightbulb" }}
                            title="Show thought process"
                            ariaLabel="Show thought process"
                            onClick={() => onThoughtProcessClicked()}
                            disabled={!answer.choices[0].context.thoughts?.length}
                        />
                    </div>
                </Stack>
            </Stack.Item>

            <Stack.Item grow>
                <div className={styles.answerText}>
                    <Markdown
                        remarkPlugins={[remarkGfm]}
                        children={messageContent}
                        components={{
                            code(props) {
                                const {children, className, node, ...rest} = props
                                const match = /language-(\w+)/.exec(className || '')
                                return match ? (
                                <SyntaxHighlighter
                                    null
                                    PreTag="div"
                                    children={String(children).replace(/\n$/, '')}
                                    language={match[1]}
                                    style={vs}
                                />
                                ) : (
                                <code {...rest} className={className}>
                                    {children}
                                </code>
                                )
                            }
                        }}
                    />
                </div>
            </Stack.Item>
        </Stack>
    );
};
